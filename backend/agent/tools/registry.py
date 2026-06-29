"""tool_registry — Agent → Tool 映射表 + OpenAI schema 转换

职责：
1. 全局工具表（BaseTool 实例，通过 register_tool 注册）
2. Agent → 可用工具集映射（AGENT_TOOLS 白名单）
3. BaseTool → OpenAI tools JSON schema 转换
4. 工具可见性过滤（LLM 只能调 Agent 可见的工具）

扩展点：
- 新增 Agent：在 AGENT_TOOLS 加一行
- 新增 Tool：在对应 tools/*.py 末尾调 register_tool()，
             在 AGENT_TOOLS 对应 agent 列表里加 tool name
- ToolRegistry.register_agent_tools()：运行时动态授权（测试/插件用）
"""
from __future__ import annotations

import logging
from pydantic import BaseModel
from typing import Dict, List, Optional

from backend.agent.tools.base import BaseTool, get_tool

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════
#  Agent → Tool 白名单
# ══════════════════════════════════════════════════════

AGENT_TOOLS: Dict[str, List[str]] = {
    # ── 管家（唯一用户入口，ReAct loop）──────────────────
    # 职责内：项目 CRUD、Onboarding 推进、基座编辑、图片生成、探索度
    # 职责外：通过 delegate_to_agent（同步）/ dispatch_background_task（异步）委托专家
    "novel_steward": [
        "load_project",
        "create_project",
        "delete_project",              # v0.6.2 补：删除项目（软删 → .trash/）
        "edit_artifact",
        "generate_image",
        "update_exploration_level",    # v0.6.2 补：调整项目/全局探索度
        "list_style_packs",            # 查询可用笔风列表（Onboarding/调整笔风时先读）
        "adjust_style",                # 写入/更新 style_pack_id
        "onboarding_propose_step",
        "onboarding_user_confirm",
        "onboarding_generate_chapter",
        "delegate_to_agent",           # 同步委托专家（用户等待结果）
        "dispatch_background_task",    # 异步派发后台任务（管家自主识别）
    ],
    # ── 文笔家（ReAct loop：调 LLM 写正文 + 调 generate_chapter/summarize_chapter 工具落盘）────────────
    # v0.6.2 重构：文笔家不再直接被外层调用解析 final_response，所有章节生成都走 ReAct loop
    # 由 LLM 自主决定调 generate_chapter / summarize_chapter 工具落盘
    "novel_writer": [
        "load_project",
        "read_chapter",
        "generate_chapter",       # v0.6.2 新增：纯落盘（写文件 + 入 DB）
        "summarize_chapter",      # v0.6.2 新增：抽 1 句话 summary
    ],
    # ── 世界树管理（可调多 tool 自主推演）──────────────
    "world_tree_manager": [
        "load_project",
        "edit_artifact",
        "update_base",
        "weave_plot",
        "introspect_character",
        "adjust_style",
        "switch_pov",
    ],
}


# ══════════════════════════════════════════════════════
#  ToolRegistry 主类
# ══════════════════════════════════════════════════════

class ToolRegistry:
    """工具注册表（Agent → Tool 映射 + OpenAI schema 转换）

    使用方式：
        registry = get_tool_registry()
        tools = registry.get_agent_tools("world_tree_manager")
        openai_tools = registry.to_openai_tools("world_tree_manager")

    运行时动态授权（测试 / 插件场景）：
        registry.register_agent_tools("novel_steward", ["my_new_tool"])
    """

    def __init__(self) -> None:
        # 运行时覆盖表（优先于 AGENT_TOOLS 常量）
        self._overrides: Dict[str, List[str]] = {}

    # ── 查询接口 ─────────────────────────────────────

    def get_agent_tools(self, agent_name: str) -> List[BaseTool]:
        """获取 Agent 可用的 tool 实例列表"""
        tool_names = self._resolve_tool_names(agent_name)
        if not tool_names:
            log.warning("tool_registry: 未知或无工具的 agent_name '%s'", agent_name)
            return []

        tools = []
        for name in tool_names:
            try:
                tools.append(get_tool(name))
            except KeyError:
                log.warning(
                    "tool_registry: agent '%s' 配置的工具 '%s' 未注册（跳过）",
                    agent_name, name,
                )
        return tools

    def to_openai_tools(self, agent_name: str) -> List[dict]:
        """转 OpenAI function-calling tools 格式"""
        tools = self.get_agent_tools(agent_name)
        return [_base_tool_to_openai(t) for t in tools]

    def has_tool(self, agent_name: str, tool_name: str) -> bool:
        """检查 Agent 是否能用某个 tool（执行前权限校验）"""
        return tool_name in self._resolve_tool_names(agent_name)

    def get_agent_tool_names(self, agent_name: str) -> List[str]:
        """获取 Agent 可用的 tool 名字列表"""
        return list(self._resolve_tool_names(agent_name))

    def list_agents(self) -> List[str]:
        """列出所有已配置的 Agent 名"""
        agents = set(AGENT_TOOLS.keys()) | set(self._overrides.keys())
        return sorted(agents)

    # ── 运行时动态授权 ────────────────────────────────

    def register_agent_tools(
        self,
        agent_name: str,
        tool_names: List[str],
        replace: bool = False,
    ) -> None:
        """运行时给 Agent 动态授权 tool（测试/插件/临时扩展）

        Args:
            agent_name: Agent 名
            tool_names: 要授权的 tool 名列表
            replace: True = 完全替换该 Agent 的工具列表；False = 追加到白名单末尾
        """
        if replace:
            self._overrides[agent_name] = list(tool_names)
            log.info(
                "tool_registry: agent '%s' 工具列表已替换为 %s",
                agent_name, tool_names,
            )
        else:
            existing = list(self._resolve_tool_names(agent_name))
            added = [t for t in tool_names if t not in existing]
            self._overrides[agent_name] = existing + added
            log.info(
                "tool_registry: agent '%s' 追加工具 %s（总计 %d 个）",
                agent_name, added, len(self._overrides[agent_name]),
            )

    def reset_overrides(self, agent_name: Optional[str] = None) -> None:
        """清除运行时覆盖（测试用）

        Args:
            agent_name: 指定 Agent 清除；None = 清除所有覆盖
        """
        if agent_name:
            self._overrides.pop(agent_name, None)
        else:
            self._overrides.clear()

    # ── 内部 ─────────────────────────────────────────

    def _resolve_tool_names(self, agent_name: str) -> List[str]:
        """优先返回运行时覆盖，否则返回静态白名单"""
        if agent_name in self._overrides:
            return self._overrides[agent_name]
        return AGENT_TOOLS.get(agent_name, [])


# ══════════════════════════════════════════════════════
#  BaseTool → OpenAI JSON schema 转换
# ══════════════════════════════════════════════════════

def _pydantic_to_json_schema(model: type[BaseModel]) -> dict:
    """Pydantic v2 BaseModel → OpenAI function parameters JSON schema"""
    schema = model.model_json_schema()
    cleaned: dict = {
        "type": schema.get("type", "object"),
        "properties": schema.get("properties", {}),
    }
    if "required" in schema:
        cleaned["required"] = schema["required"]
    if "description" in schema:
        cleaned["description"] = schema["description"]
    # $defs 不在 OpenAI schema 中；当前所有 tool schema 均为 flat，无需展开
    return cleaned


def _base_tool_to_openai(tool: BaseTool) -> dict:
    """单个 BaseTool → OpenAI tool dict"""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": _pydantic_to_json_schema(tool.input_schema),
        },
    }


# ══════════════════════════════════════════════════════
#  Tool 调用结果包装（发给 LLM 的 tool message）
# ══════════════════════════════════════════════════════

def make_tool_message(
    tool_call_id: str,
    tool_name: str,
    result: dict | str,
) -> dict:
    """把 tool 执行结果包装成 LLM message（role=tool）"""
    if isinstance(result, dict):
        import json
        content = json.dumps(result, ensure_ascii=False)
    else:
        content = str(result)

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": content,
    }


# ══════════════════════════════════════════════════════
#  工厂方法（单例）
# ══════════════════════════════════════════════════════

_registry_instance: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取单例 ToolRegistry"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
    return _registry_instance


# ══════════════════════════════════════════════════════
#  自检（python -m backend.agent.tools.registry）
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    # 触发所有 tool 模块 import，使 register_tool 生效
    import backend.agent.tools.chapter_tools      # noqa: F401
    import backend.agent.tools.project_tools      # noqa: F401
    import backend.agent.tools.memory_tools       # noqa: F401
    import backend.agent.tools.image_tools        # noqa: F401
    import backend.agent.tools.onboarding_tools   # noqa: F401
    import backend.agent.tools.delegation_tools   # noqa: F401
    import backend.agent.tools.base_edit_tools    # noqa: F401
    import backend.agent.tools.edit_artifact_tool # noqa: F401

    registry = get_tool_registry()

    for agent_name in registry.list_agents():
        tools = registry.get_agent_tools(agent_name)
        openai_tools = registry.to_openai_tools(agent_name)
        print(f"\n=== {agent_name} ({len(tools)} tools) ===")
        print(f"  工具: {[t.name for t in tools]}")
        if openai_tools:
            print(f"  OpenAI schema 示例（第1个）:")
            print(f"  {json.dumps(openai_tools[0], ensure_ascii=False, indent=2)}")
