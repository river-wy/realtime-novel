"""tool_registry — Agent → Tool 映射表 + OpenAI schema 转换（s3.2）

职责（spec.md §9.2）：
1. 全局工具表（14 个 BaseTool 实例）
2. Agent → 可用工具集映射（spec.md §3.5）
3. BaseTool → OpenAI tools JSON schema 转换
4. 工具可见性过滤（LLM 只能调 Agent 可见的工具）

对应 spec.md §9.2 ToolRegistry
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from pydantic import BaseModel

from backend.agent.tools.base import BaseTool, get_tool, list_tools

log = logging.getLogger(__name__)


# ============ Agent → Tool 映射表（spec.md §3.5）============

# 18:02 拍板
AGENT_TOOLS: Dict[str, List[str]] = {
    # 管家（v0.6.1: 统一 chat 模式, ReAct loop, 包含 Onboarding 推进工具）
    "novel_steward": [
        "load_project",
        "search_memory",
        "create_project",
        "edit_artifact",
        "generate_image",
        "onboarding_propose_step",
        "onboarding_user_confirm",
        "onboarding_generate_chapter",
    ],
    # 文笔家（只读 tool，不改基座）
    "novel_writer": [
        "search_memory",
        "load_project",
        "read_chapter",
    ],
    # 世界树管理（可调多 tool 自主推演）
    "world_tree_manager": [
        "search_memory",
        "load_project",
        "edit_artifact",
        "update_base",
        "weave_plot",
        "introspect_character",
        "adjust_style",
        "switch_pov",
    ],
}


# ============ ToolRegistry 主类 ============

class ToolRegistry:
    """工具注册表（Agent → Tool 映射 + OpenAI schema 转换）

    使用方式：
        registry = get_tool_registry()
        # 1. 获取 Agent 可用的 tool 实例
        tools = registry.get_agent_tools("world_tree_manager")
        # 2. 转 OpenAI tools 格式（注入 LLMRequest.tools）
        openai_tools = registry.to_openai_tools("world_tree_manager")
    """

    def get_agent_tools(self, agent_name: str) -> List[BaseTool]:
        """获取 Agent 可用的 tool 实例列表

        Args:
            agent_name: Agent 名（novel_steward / novel_writer / world_tree_manager）

        Returns:
            BaseTool 实例列表（已实例化）
        """
        tool_names = AGENT_TOOLS.get(agent_name, [])
        if not tool_names:
            log.warning(f"tool_registry: 未知 agent_name '{agent_name}'")
            return []

        tools = []
        for name in tool_names:
            try:
                tools.append(get_tool(name))
            except KeyError:
                log.warning(f"tool_registry: agent '{agent_name}' 配置的工具 '{name}' 未注册")

        return tools

    def to_openai_tools(self, agent_name: str) -> List[dict]:
        """转 OpenAI tools 格式（注入到 LLMRequest.tools）

        OpenAI 格式：
        [
          {
            "type": "function",
            "function": {
              "name": "search_memory",
              "description": "...",
              "parameters": {JSON schema}
            }
          },
          ...
        ]
        """
        tools = self.get_agent_tools(agent_name)
        return [_base_tool_to_openai(t) for t in tools]

    def has_tool(self, agent_name: str, tool_name: str) -> bool:
        """检查 Agent 是否能用某个 tool（用于权限校验）"""
        return tool_name in AGENT_TOOLS.get(agent_name, [])

    def get_agent_tool_names(self, agent_name: str) -> List[str]:
        """获取 Agent 可用的 tool 名字列表"""
        return list(AGENT_TOOLS.get(agent_name, []))


# ============ BaseTool → OpenAI JSON schema 转换 ============

def _pydantic_to_json_schema(model: type[BaseModel]) -> dict:
    """Pydantic v2 BaseModel → OpenAI JSON schema

    复用 model_json_schema()，去掉 Pydantic 专属字段（$defs 等）
    """
    schema = model.model_json_schema()

    # 清理：移除 Pydantic 特有但 OpenAI 不需要的字段
    cleaned = {
        "type": schema.get("type", "object"),
        "properties": schema.get("properties", {}),
    }
    if "required" in schema:
        cleaned["required"] = schema["required"]
    if "description" in schema:
        cleaned["description"] = schema["description"]
    # 注意：$defs 不在 OpenAI function calling schema 中，需要内联展开
    # 简化处理：v0.6 s3 阶段假设所有 schema 都是 flat（无嵌套 $ref）
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


# ============ Tool 调用结果包装（发给 LLM 的 tool message）============

def make_tool_message(
    tool_call_id: str,
    tool_name: str,
    result: dict | str,
) -> dict:
    """把 tool 执行结果包装成 LLM message（role=tool）

    Returns:
        {"role": "tool", "tool_call_id": "...", "content": "..."}
    """
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


# ============ 工厂方法 ============

_registry_instance: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取单例 ToolRegistry"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
    return _registry_instance


# ============ 测试 ============

if __name__ == "__main__":
    """自检：3 Agent 的工具集 + OpenAI schema 转换"""
    import json
    registry = get_tool_registry()

    for agent_name in ["novel_steward", "novel_writer", "world_tree_manager"]:
        tools = registry.get_agent_tools(agent_name)
        openai_tools = registry.to_openai_tools(agent_name)
        print(f"\n=== {agent_name} ===")
        print(f"  工具数: {len(tools)}")
        print(f"  工具名: {[t.name for t in tools]}")
        print(f"  OpenAI schema 示例:")
        print(f"  {json.dumps(openai_tools[0], ensure_ascii=False, indent=2) if openai_tools else '(empty)'}")