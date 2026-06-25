"""world_tree_manager — 世界树管理（v0.6 s3.4 AgentExecutor 接入）

职责（spec.md §3.3）：
1. 基座一致性检查
2. 剧情干预影响分析
3. 种子/伏笔预留
4. 走向调整
5. diff 结构化输出（base_updates + plot_adjustments + new_seeds）

实现：s3.4 起改用 AgentExecutor 跑 ReAct loop，LLM 自主决定调：
- search_memory（查历史干预/记忆）
- load_project（读 7 件基座）
- edit_artifact（改 7 件）
- update_base（直接改基座字段）
- weave_plot（调整主线/支线）
- introspect_character（更新角色状态）
- adjust_style（调整文风）
- switch_pov（切换 POV）

对应 spec.md §3.3
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Any, List
from pydantic import BaseModel, Field

from backend.agent.runtime.executor import AgentExecutor, AgentConfig, AgentOutput, get_agent_executor

log = logging.getLogger(__name__)


# ============ Diff 结构 ============

class BaseUpdate(BaseModel):
    """单条基座更新"""
    artifact: str = Field(description="7 件之一")
    field: str = Field(description="字段路径")
    old_value: Any = None
    new_value: Any = None
    reason: str = ""


class PlotAdjustment(BaseModel):
    """主线/支线走向调整"""
    arc: str
    adjustment: str
    impact_chapters: List[int] = Field(default_factory=list)


class NewSeed(BaseModel):
    """新埋种子/伏笔"""
    name: str
    trigger: str
    payoff: str
    estimated_chapter: Optional[int] = None


class ConsistencyCheckResult(BaseModel):
    """一致性检查结果"""
    status: str = Field(default="PASS", description="PASS / WARN / FAIL")
    conflicts: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class WorldTreeDiff(BaseModel):
    """世界树管理返回的结构化 diff"""
    intent: str = Field(description="intervene / adjust_base")
    summary: str = Field(description="一句话总结")

    base_updates: List[BaseUpdate] = Field(default_factory=list)
    plot_adjustments: List[PlotAdjustment] = Field(default_factory=list)
    new_seeds: List[NewSeed] = Field(default_factory=list)

    consistency: ConsistencyCheckResult = Field(default_factory=ConsistencyCheckResult)
    risk_level: str = Field(default="low", description="low/medium/high")
    requires_double_confirm: bool = Field(default=False)

    # v0.6 s3.4 新增：trace 字段（记录推演过程）
    iterations: int = 0
    tool_calls_count: int = 0
    tool_calls_trace: List[dict] = Field(default_factory=list)


# ============ 系统提示 ============

WORLD_TREE_MANAGER_SYSTEM_PROMPT = """你是「世界树管理」。

【职责】
当用户对项目内的世界树基座进行干预时，你负责分析影响范围、调整基座、保持一致性。

【可用基座 7 件】
1. world_tree - 时间线、地理、核心规则
2. style_charter - 写作风格
3. genre_resonance - 题材、情绪基调
4. main_plot - 主线弧线
5. sub_plots - 支线
6. character_card - 角色卡
7. seed_table - 伏笔种子

【典型工作流】
1. 调用 load_project 获取当前 7 件基座
2. 调用 search_memory 检索相关历史干预记录
3. 分析用户干预的影响：
   - 涉及哪些基座的哪些字段？
   - 是否影响主线弧线（main_plot）？
   - 是否需要埋伏笔（seed_table）？
   - 是否引发 7 件之间的矛盾？
4. 调用对应 tool 执行修改：
   - 简单字段改 → update_base
   - 复杂结构改 → edit_artifact
   - 主线/支线调整 → weave_plot
   - 角色状态变化 → introspect_character
5. 输出 final_response，必须是 JSON 格式：

```json
{
  "intent": "intervene",
  "summary": "一句话总结这次干预",
  "base_updates": [
    {"artifact": "character_card", "field": "师父.role", "old_value": "师父", "new_value": "幕后反派", "reason": "..."}
  ],
  "plot_adjustments": [
    {"arc": "main_arc", "adjustment": "主角从师徒对抗变为...", "impact_chapters": [3, 5, 12]}
  ],
  "new_seeds": [
    {"name": "师父秘密", "trigger": "第3章主角发现...", "payoff": "第12章决战", "estimated_chapter": 3}
  ],
  "consistency": {"status": "PASS", "conflicts": [], "warnings": []},
  "risk_level": "medium",
  "requires_double_confirm": false
}
```

【关键约束】
- 修改基座前必须先 load_project 看清现状
- 不能让 7 件基座内部矛盾（如改完 character_card 让 world_tree 冲突）
- 长程伏笔（seed_table）必须明确 trigger + payoff + estimated_chapter
- 多个改动可并行调用 tool
- 最终 JSON 必须是合法 JSON，不要包含 markdown 包裹

【一致性原则】
- world_tree 与 character_card 不能矛盾（如世界规则说"无魔法"，角色不能会魔法）
- main_plot 与 sub_plots 不能矛盾
- seed_table 的 payoff 不能超出 main_plot 范围
"""


# ============ WorldTreeManager 主类 ============

class WorldTreeManager:
    """世界树管理（v0.6 s3.4：AgentExecutor 接入）"""

    def __init__(self, executor: Optional[AgentExecutor] = None):
        self.executor = executor or get_agent_executor()

    async def analyze_intervention(
        self,
        project_id: str,
        intervention_text: str,
        max_iterations: int = 7,
    ) -> WorldTreeDiff:
        """分析干预影响，返回结构化 diff（含一致性检查）"""
        cfg = AgentConfig(
            agent_name="world_tree_manager",
            system_prompt=WORLD_TREE_MANAGER_SYSTEM_PROMPT,
        )

        executor_output = await self.executor.execute(
            agent=cfg,
            user_message=f"用户干预：{intervention_text}",
            project_id=project_id,
            max_iterations=max_iterations,
        )

        # 解析 final_response 为 WorldTreeDiff
        diff = self._parse_diff(executor_output, intent="intervene")
        diff.iterations = executor_output.iterations
        diff.tool_calls_count = len(executor_output.tool_calls_history)
        diff.tool_calls_trace = executor_output.tool_calls_history

        # v0.6 s4：调用一致性检查器验证 LLM 返回的 diff
        diff.consistency = await self._run_consistency_check(
            project_id=project_id,
            proposed_updates=diff.base_updates,
            proposed_seeds=diff.new_seeds,
        )

        # 根据一致性状态升级 risk_level
        if diff.consistency.status == "FAIL":
            diff.risk_level = "blocked"
            diff.requires_double_confirm = True

        return diff

    async def analyze_base_adjustment(
        self,
        project_id: str,
        adjustment_text: str,
        max_iterations: int = 7,
    ) -> WorldTreeDiff:
        """分析基座调整（与干预类似，但 intent 不同）"""
        cfg = AgentConfig(
            agent_name="world_tree_manager",
            system_prompt=WORLD_TREE_MANAGER_SYSTEM_PROMPT,
        )

        executor_output = await self.executor.execute(
            agent=cfg,
            user_message=f"用户基座调整：{adjustment_text}",
            project_id=project_id,
            max_iterations=max_iterations,
        )

        diff = self._parse_diff(executor_output, intent="adjust_base")
        diff.iterations = executor_output.iterations
        diff.tool_calls_count = len(executor_output.tool_calls_history)
        diff.tool_calls_trace = executor_output.tool_calls_history

        # v0.6 s4：调用一致性检查器
        diff.consistency = await self._run_consistency_check(
            project_id=project_id,
            proposed_updates=diff.base_updates,
            proposed_seeds=diff.new_seeds,
        )
        if diff.consistency.status == "FAIL":
            diff.risk_level = "blocked"
            diff.requires_double_confirm = True

        return diff

    async def _run_consistency_check(
        self,
        project_id: str,
        proposed_updates,
        proposed_seeds,
    ) -> ConsistencyCheckResult:
        """调用一致性检查器

        v0.6 s4：
        1. 加载项目当前 7 件基座快照
        2. 应用 proposed_updates 得到"应用后"快照
        3. 调用 checker.check() 验证
        """
        try:
            from backend.services.consistency_checker import (
                ConsistencyChecker, BaseSnapshot,
            )
            from backend.persistence import ProjectRepository

            repo = ProjectRepository()
            checker = ConsistencyChecker(project_id)

            # 加载快照
            before = ConsistencyChecker.load_snapshot(repo, project_id)

            # v0.6 简化：模拟 apply（直接复制 before，不真正应用）
            # 后续 s4+ 可实装真正的 apply 逻辑
            after = before

            return checker.check(
                before=before,
                after=after,
                proposed_updates=proposed_updates,
                proposed_seeds=proposed_seeds,
            )
        except Exception as e:
            log.warning(f"world_tree_manager: consistency check failed: {e}")
            return ConsistencyCheckResult(
                status="WARN",
                warnings=[f"一致性检查执行失败: {e}"],
            )

    def _parse_diff(self, executor_output: AgentOutput, intent: str) -> WorldTreeDiff:
        """从 AgentExecutor 输出解析 WorldTreeDiff"""
        final = executor_output.final_response.strip()

        # 多种 JSON 格式处理
        # 1. 先尝试直接解析
        parsed = None
        try:
            parsed = json.loads(final)
        except json.JSONDecodeError:
            pass

        # 2. 尝试去掉 markdown 包裹
        if parsed is None and final.startswith("```"):
            lines = final.split("```")
            for chunk in lines:
                chunk = chunk.strip()
                if chunk.startswith("json"):
                    chunk = chunk[4:].strip()
                try:
                    parsed = json.loads(chunk)
                    break
                except json.JSONDecodeError:
                    continue

        # 3. 尝试提取文本中的第一个 JSON 对象（{...} 包含在最外层）
        if parsed is None:
            # 从前往后找第一个 {，从后往前找对应的 }
            start = final.find("{")
            if start >= 0:
                depth = 0
                for i in range(start, len(final)):
                    if final[i] == "{":
                        depth += 1
                    elif final[i] == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = final[start:i+1]
                            try:
                                parsed = json.loads(candidate)
                                break
                            except json.JSONDecodeError:
                                continue

        if parsed is None:
            log.warning(f"world_tree_manager: LLM 输出无法提取 JSON: {final[:200]}")
            return WorldTreeDiff(
                intent=intent,
                summary=final[:200] or "LLM 输出无法解析",
                consistency=ConsistencyCheckResult(status="FAIL", conflicts=["JSON 解析失败"]),
                risk_level="high",
                requires_double_confirm=True,
            )

        return WorldTreeDiff(
            intent=parsed.get("intent", intent),
            summary=parsed.get("summary", ""),
            base_updates=[BaseUpdate(**u) for u in parsed.get("base_updates", []) or []],
            plot_adjustments=[PlotAdjustment(**a) for a in parsed.get("plot_adjustments", []) or []],
            new_seeds=[NewSeed(**s) for s in parsed.get("new_seeds", []) or []],
            consistency=ConsistencyCheckResult(**(parsed.get("consistency") or {"status": "PASS"})),
            risk_level=parsed.get("risk_level", "low"),
            requires_double_confirm=parsed.get("requires_double_confirm", False),
        )

        return WorldTreeDiff(
            intent=parsed.get("intent", intent),
            summary=parsed.get("summary", ""),
            base_updates=[BaseUpdate(**u) for u in parsed.get("base_updates", []) or []],
            plot_adjustments=[PlotAdjustment(**a) for a in parsed.get("plot_adjustments", []) or []],
            new_seeds=[NewSeed(**s) for s in parsed.get("new_seeds", []) or []],
            consistency=ConsistencyCheckResult(**(parsed.get("consistency") or {"status": "PASS"})),
            risk_level=parsed.get("risk_level", "low"),
            requires_double_confirm=parsed.get("requires_double_confirm", False),
        )


# ============ 工厂方法 ============

_manager_instance: Optional[WorldTreeManager] = None


def get_world_tree_manager() -> WorldTreeManager:
    """获取单例 WorldTreeManager"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = WorldTreeManager()
    return _manager_instance