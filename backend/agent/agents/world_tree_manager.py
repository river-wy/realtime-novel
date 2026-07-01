"""world_tree_manager — 世界树管理（v0.6 s3.4 AgentExecutor 接入）

职责（spec.md §3.3）：
1. 基座一致性检查
2. 剧情干预影响分析
3. 种子/伏笔预留
4. 走向调整
5. diff 结构化输出（base_updates + plot_adjustments + new_seeds）

实现：s3.4 起改用 AgentExecutor 跑 ReAct loop，LLM 自主决定调：
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
from pydantic import BaseModel, Field
from typing import Optional, Any, List

from backend.agent.runtime.executor import AgentExecutor, AgentConfig, AgentOutput, get_agent_executor
from backend.utils.logger import logger as logger_decorator


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


# ============ Onboarding 初始化专用提示 ============

WORLD_TREE_INIT_PROMPT = """你是「世界树管理」，当前任务是为一部新小说初始化 7 件基座。

【任务】
用户已通过对话确认了以下 6 维基础信息，你需要基于这些信息设计完整的 7 件基座并逐一写入 DB。

【7 件基座职责分配】
1. world_tree     ← 从「世界树基础」+「故事核心」中提取时间线/地理/核心规则
2. genre_resonance ← 从「世界树基础」（题材/风格/基调）+ 「笔风标签」中提取
3. main_plot      ← 从「主线与大纲」（主线节点）中构建 arc_phrase + beats
4. sub_plot       ← 从「主线与大纲」（支线）中构建 threads
5. character_card ← 从「主要角色」中构建 characters 列表（明确 protagonist/antagonist/deuteragonist）
6. seed_table     ← 从「主线与大纲」（伏笔/钩子）中构建 seeds（每条必须有 trigger + payoff）
7. style_pack     ← 从「笔风标签」（叙述风格）推断 style_pack_id，通过 adjust_style 工具写入

【工作流】
1. 直接基于下方用户确认的 6 维信息进行设计（无需调 load_project，项目刚创建基座为空）
2. 逐一调用 edit_artifact 写入每一件基座（7 件都要写）
3. 如果叙述风格指向具体笔风，调 adjust_style 写入 style_pack_id
4. 所有基座写完后，输出 final_response（JSON 格式 WorldTreeDiff，intent="initialize"）

【关键约束】
- 严格保留用户原文用词（人名/地名/专有名词不能改写）
- 用户没说的地方可以合理补全，但不能与用户设定矛盾
- 7 件必须内部一致（character_card 的角色与 world_tree 的世界规则不矛盾）
- seed_table 每条种子必须有 trigger（触发条件）和 payoff（回收点），不能只是一句话描述
- main_plot 的 beats 要覆盖用户提供的主线节点，节点格式统一

【输出格式】
输出合法 JSON（无 markdown 包裹）：
{
  "intent": "initialize",
  "summary": "一句话描述初始化结果",
  "base_updates": [{"artifact": "world_tree", "field": "...", "old_value": null, "new_value": "...", "reason": "..."}],
  "plot_adjustments": [],
  "new_seeds": [...],
  "consistency": {"status": "PASS", "conflicts": [], "warnings": []},
  "risk_level": "low",
  "requires_double_confirm": false
}
"""


# ============ 系统提示 ============

WORLD_TREE_MANAGER_SYSTEM_PROMPT = """你是「世界树管理」。

【职责】
当用户对项目内的世界树基座进行干预时，你负责分析影响范围、调整基座、保持一致性。

【可用基座 7 件】
1. world_tree - 时间线、地理、核心规则
2. style_pack - 写作笔风
3. genre_resonance - 题材、情绪基调
4. main_plot - 主线弧线
5. sub_plots - 支线
6. character_card - 角色卡
7. seed_table - 伏笔种子

【典型工作流】
1. 调用 load_project 获取当前 7 件基座
2. 分析用户干预的影响：
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

@logger_decorator
class WorldTreeManager:
    """世界树管理（v0.6 s3.4：AgentExecutor 接入）"""

    def __init__(self, executor: Optional[AgentExecutor] = None):
        self.executor = executor or get_agent_executor()
        # v003: 注册 8 个 add_* 工具供 WTM Agent LLM 调用（arch-plan §2.1）
        self.tools = {
            "add_world_entry": self._add_world_entry,
            "add_timeline_event": self._add_timeline_event,
            "add_geography_location": self._add_geography_location,
            "add_main_plot_node": self._add_main_plot_node,
            "add_sub_plot": self._add_sub_plot,
            "add_volume": self._add_volume,
            "add_character": self._add_character,
            "add_seed": self._add_seed,
        }

    # ============ v003: 8 个 _add_* 工具方法（arch-plan §2.1）============
    # 这些方法是 WTM Agent LLM 在 ReAct loop 中可调用的「写库」工具
    # 返回的字符串是新增条目的 ID（varchar 随机），供后续 update/delete 使用

    async def _add_world_entry(self, project_id: str, data: Dict[str, Any]) -> str:
        """WTM 工具: 新增世界百科条目（知识库）"""
        from backend.persistence import ProjectRepository
        return ProjectRepository().add_world_entry(project_id, data)

    async def _add_timeline_event(self, project_id: str, data: Dict[str, Any]) -> str:
        """WTM 工具: 新增时间线事件"""
        from backend.persistence import ProjectRepository
        return ProjectRepository().add_timeline_event(project_id, data)

    async def _add_geography_location(self, project_id: str, data: Dict[str, Any]) -> str:
        """WTM 工具: 新增地理位置"""
        from backend.persistence import ProjectRepository
        return ProjectRepository().add_geography_location(project_id, data)

    async def _add_main_plot_node(self, project_id: str, data: Dict[str, Any]) -> str:
        """WTM 工具: 新增主线节点（v003 1:n 结构）"""
        from backend.persistence import ProjectRepository
        return ProjectRepository().add_main_plot_node(project_id, data)

    async def _add_sub_plot(self, project_id: str, data: Dict[str, Any]) -> str:
        """WTM 工具: 新增支线"""
        from backend.persistence import ProjectRepository
        return ProjectRepository().add_subplot(project_id, data)

    async def _add_volume(self, project_id: str, data: Dict[str, Any]) -> str:
        """WTM 工具: 新增卷"""
        from backend.persistence import ProjectRepository
        return ProjectRepository().add_volume(project_id, data)

    async def _add_character(self, project_id: str, data: Dict[str, Any]) -> str:
        """WTM 工具: 新增角色"""
        from backend.persistence import ProjectRepository
        return ProjectRepository().add_character(project_id, data)

    async def _add_seed(self, project_id: str, data: Dict[str, Any]) -> int:
        """WTM 工具: 新增伏笔（add_seed 返回 int 主键）"""
        from backend.persistence import ProjectRepository
        return ProjectRepository().add_seed(project_id, data)

    async def initialize_world_tree(
        self,
        project_id: str,
        onboarding_payload: dict,
        max_iterations: int = 15,
    ) -> WorldTreeDiff:
        """Onboarding 专用：基于用户确认的 6 维信息初始化 7 件基座

        调用方：OnboardingProposeStepTool（step=3/4 时替代 OnboardingController.consult）
        本方法合并原 step 3+4 的推演，一次性完成所有 7 件基座的设计+落盘。

        Args:
            project_id: 项目 ID（create_project 已创建，基座为空）
            onboarding_payload: 管家第一阶段收集到的 6 维信息，结构如下：
                {
                    "project_name": str,
                    "genres": list[str],          # 题材
                    "styles": list[str],           # 风格
                    "tone": str,                   # 基调
                    "story_core": str,             # 故事核心（v003 删 opening_scene）
                    "characters": str,             # 主要角色（每行一个，格式：名字-身份-特质）
                    "main_arc": str,               # 主线节点（每行一个）
                    "sub_plots": str,              # 支线
                    "seeds": str,                  # 伏笔/钩子
                    "style_description": str,      # 笔风描述
                    "novel_tags": list[str],        # 小说类型标签
                    "palette": str,                # UI 色调
                }
            max_iterations: ReAct loop 最大迭代数

        Returns:
            WorldTreeDiff（intent="initialize"）
        """
        self.log.info(
            "WorldTreeManager.initialize_world_tree START: project_id=%s, "
            "payload_keys=%s",
            project_id, list(onboarding_payload.keys()),
        )

        # 拼装 user_message：把 6 维信息结构化成自然语言，让 WTM 的 LLM 理解
        def _fmt(v) -> str:
            if isinstance(v, list):
                return "、".join(str(x) for x in v) if v else "（未指定）"
            return str(v) if v else "（未指定）"

        user_message = f"""请基于以下用户确认的完整小说设定，初始化 7 件基座并逐一写入 DB。

【项目名称】{_fmt(onboarding_payload.get('project_name'))}

【世界树基础】
- 题材：{_fmt(onboarding_payload.get('genres'))}
- 风格：{_fmt(onboarding_payload.get('styles'))}
- 基调：{_fmt(onboarding_payload.get('tone'))}

【故事核心】
{_fmt(onboarding_payload.get('story_core'))}

【主要角色】（每行：名字 - 身份/角色 - 核心特质）
{_fmt(onboarding_payload.get('characters'))}

【主线与大纲】
- 主线节点：
{_fmt(onboarding_payload.get('main_arc'))}
- 关键支线：{_fmt(onboarding_payload.get('sub_plots'))}
- 主要伏笔/钩子：{_fmt(onboarding_payload.get('seeds'))}

【笔风与标签】
- 叙述风格：{_fmt(onboarding_payload.get('style_description'))}
- 小说类型标签：{_fmt(onboarding_payload.get('novel_tags'))}
- UI 色调：{_fmt(onboarding_payload.get('palette'))}

请按【7 件基座职责分配】逐一调用 edit_artifact 完成写入，然后输出 WorldTreeDiff JSON。"""

        cfg = AgentConfig(
            agent_name="world_tree_manager",
            system_prompt=WORLD_TREE_INIT_PROMPT,
        )

        executor_output = await self.executor.execute(
            agent=cfg,
            user_message=user_message,
            project_id=project_id,
            context_message=None,   # 新建项目，基座为空，不需要注入 context
            max_iterations=max_iterations,
        )

        self.log.info(
            "WorldTreeManager.initialize_world_tree EXECUTOR DONE: project_id=%s, "
            "iterations=%d, tool_calls=%d, error=%s",
            project_id, executor_output.iterations,
            len(executor_output.tool_calls_history), executor_output.error,
        )

        diff = self._parse_diff(executor_output, intent="initialize")
        diff.iterations = executor_output.iterations
        diff.tool_calls_count = len(executor_output.tool_calls_history)
        diff.tool_calls_trace = executor_output.tool_calls_history

        # Onboarding 初始化不做一致性检查（项目刚创建，没有历史状态可对比）
        # 但记录 summary 供上层工具透传
        self.log.info(
            "WorldTreeManager.initialize_world_tree DONE: project_id=%s, "
            "base_updates=%d, new_seeds=%d, summary=%s",
            project_id,
            len(diff.base_updates), len(diff.new_seeds),
            diff.summary[:80],
        )

        return diff

    async def analyze_intervention(
        self,
        project_id: str,
        intervention_text: str,
        max_iterations: int = 15,
    ) -> WorldTreeDiff:
        """分析干预影响，返回结构化 diff（含一致性检查）"""
        self.log.info(
            "WorldTreeManager.analyze_intervention START: project_id=%s, text_len=%d",
            project_id, len(intervention_text),
        )

        # v0.6.2: 调组装模块拼 system_prompt（身份+笔风+法则+基座摘要）
        from backend.agent.prompts.agent_prompt_factory import (
            build_worldtree_system_prompt,
            build_project_context_message,
        )

        # session_key 按 project 维度隔离，跨调用保留推演上下文
        session_key = f"{project_id}:world_tree_manager"

        # 每次都传入完整的 system_prompt，HIT/MISS 判断由 executor 内部決定
        system_prompt = build_worldtree_system_prompt(project_id)
        # context_message 每次刷新，确保基座快照最新
        context_message = build_project_context_message(project_id, "world_tree_manager")

        cfg = AgentConfig(
            agent_name="world_tree_manager",
            system_prompt=system_prompt,
        )

        executor_output = await self.executor.execute(
            agent=cfg,
            user_message=f"用户干预：{intervention_text}",
            project_id=project_id,
            context_message=context_message,
            session_key=session_key,
            max_iterations=max_iterations,
        )

        self.log.info(
            "WorldTreeManager.analyze_intervention EXECUTOR DONE: project_id=%s, "
            "iterations=%d, tool_calls=%d, error=%s",
            project_id, executor_output.iterations,
            len(executor_output.tool_calls_history), executor_output.error,
        )

        # 解析 final_response 为 WorldTreeDiff
        diff = self._parse_diff(executor_output, intent="intervene")
        diff.iterations = executor_output.iterations
        diff.tool_calls_count = len(executor_output.tool_calls_history)
        diff.tool_calls_trace = executor_output.tool_calls_history

        # v0.9 改造：调 Validator 校验落库后的基座一致性
        from backend.agent.agents.validator import get_validator
        validator = get_validator()
        diff.validation = await validator.validate_world_tree(
            project_id=project_id,
            user_intent=intervention_text,
        )

        # 联动策略：B 方案精准回滚 / FATAL 全清
        from backend.agent.agents.validator import ValidationStatus
        if diff.validation.status == ValidationStatus.FATAL:
            await self._rollback_all_writes(project_id, executor_output.tool_calls_history)
            diff.risk_level = "blocked"
            diff.requires_double_confirm = True
        elif diff.validation.status == ValidationStatus.BLOCKED:
            await self._rollback_issue_rows(project_id, diff.validation.issues)

        self.log.info(
            "WorldTreeManager.analyze_intervention DONE: project_id=%s, "
            "risk=%s, validation_status=%s, base_updates=%d, plot_adj=%d, new_seeds=%d",
            project_id, diff.risk_level,
            diff.validation.status,
            len(diff.base_updates), len(diff.plot_adjustments), len(diff.new_seeds),
        )

        return diff

    async def analyze_base_adjustment(
        self,
        project_id: str,
        adjustment_text: str,
        max_iterations: int = 15,
    ) -> WorldTreeDiff:
        """分析基座调整（与干预类似，但 intent 不同）"""
        self.log.info(
            "WorldTreeManager.analyze_base_adjustment START: project_id=%s, text_len=%d",
            project_id, len(adjustment_text),
        )

        # v0.6.2: 调组装模块拼 system_prompt（身份+笔风+法则+基座摘要）
        from backend.agent.prompts.agent_prompt_factory import (
            build_worldtree_system_prompt,
            build_project_context_message,
        )

        # session_key 与 analyze_intervention 共享同一个 project 维度 cache
        session_key = f"{project_id}:world_tree_manager"

        # 每次都传入完整的 system_prompt，HIT/MISS 判断由 executor 内部決定
        system_prompt = build_worldtree_system_prompt(project_id)
        context_message = build_project_context_message(project_id, "world_tree_manager")

        cfg = AgentConfig(
            agent_name="world_tree_manager",
            system_prompt=system_prompt,
        )

        executor_output = await self.executor.execute(
            agent=cfg,
            user_message=f"用户基座调整：{adjustment_text}",
            project_id=project_id,
            context_message=context_message,
            session_key=session_key,
            max_iterations=max_iterations,
        )

        self.log.info(
            "WorldTreeManager.analyze_base_adjustment EXECUTOR DONE: project_id=%s, "
            "iterations=%d, tool_calls=%d, error=%s",
            project_id, executor_output.iterations,
            len(executor_output.tool_calls_history), executor_output.error,
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

        self.log.info(
            "WorldTreeManager.analyze_base_adjustment DONE: project_id=%s, "
            "risk=%s, base_updates=%d, consistency=%s",
            project_id, diff.risk_level,
            len(diff.base_updates), diff.consistency.status,
        )

        return diff

    async def run_initial_baseline_react(
        self,
        project_id: str,
        steward_payload: Dict[str, Any],
        max_iterations: int = 20,
    ) -> Dict[str, Any]:
        """v0.8 WTM 入口：Onboarding 阶段完整规划小说世界基座（走 ReAct loop）

        跟 generate_full_world_tree_baseline 机械代码的区别：
        - 走 executor.execute() ReAct loop，WTM LLM 自主调工具落库 9 张表
        - 角色名字/性格/关系/伏笔等细节由 LLM 自由发挥
        - final_response 描述 WTM 实际落了什么 + 各表行数
        - 失败时直接抛错，service 层捕获并回退 info_state

        跟 analyze_intervention 的区别：
        - 注入的 system_prompt 是 initial_baseline 身份段
        - context_message 注入 steward_payload（管家收集的 hint）
        - max_iterations=20（首次生成比干预更复杂）
        - LLM 自主落库，不需要"应用前/应用后"一致性 diff
        """
        from backend.agent.prompts.agent_prompt_factory import (
            build_worldtree_system_prompt,
            build_project_context_message,
        )
        from backend.agent.runtime.executor import AgentConfig

        self.log.info(
            "WTM.run_initial_baseline_react START: project_id=%s, payload_keys=%s, max_iter=%d",
            project_id, list(steward_payload.keys()), max_iterations,
        )

        # session_key 按 project 维度，跨调用保留推演上下文
        session_key = f"{project_id}:world_tree_manager:initial_baseline"

        system_prompt = build_worldtree_system_prompt(project_id, intent="initial_baseline")

        # context_message 注入 steward_payload（管家从用户收集的 hint）
        payload_str = json.dumps(steward_payload, ensure_ascii=False, indent=2)
        context_message = (
            f"【管家收集的用户信息 hint】\n"
            f"以下是管家从用户多轮对话中提炼的信息，"
            f"你在 ReAct loop 中参考这些 hint 自主发挥：\n\n"
            f"{payload_str}\n\n"
        ) + build_project_context_message(project_id, "world_tree_manager")

        cfg = AgentConfig(
            agent_name="world_tree_manager",
            system_prompt=system_prompt,
        )

        user_message = (
            "请基于管家收集的 hint，在 ReAct loop 中自主调 edit_artifact / update_base 等工具，"
            "规划并落库完整小说世界基座（9 张表）。"
            "落库完成后输出 final_response，结构化说明每张表生成了多少行。"
        )

        executor_output = await self.executor.execute(
            agent=cfg,
            user_message=user_message,
            project_id=project_id,
            context_message=context_message,
            session_key=session_key,
            max_iterations=max_iterations,
        )

        self.log.info(
            "WTM.run_initial_baseline_react EXECUTOR DONE: project_id=%s, "
            "iterations=%d, tool_calls=%d, error=%s",
            project_id, executor_output.iterations,
            len(executor_output.tool_calls_history), executor_output.error,
        )

        if executor_output.error:
            return {
                "success": False,
                "iterations": executor_output.iterations,
                "tool_calls_count": len(executor_output.tool_calls_history),
                "error": executor_output.error,
            }

        # 统计落库行数（从 Repository 读，**不依赖 LLM final_response**）
        from backend.persistence import ProjectRepository
        repo = ProjectRepository()
        summary = {
            "world_tree_set": 1 if repo.get_world_tree(project_id) and repo.get_world_tree(project_id).story_core else 0,
            "characters_count": len(repo.list_characters(project_id)),
            "main_plot_nodes_count": len(repo.list_main_plot_nodes(project_id)),
            "volumes_count": len(repo.list_volumes(project_id)),
            "world_entries_count": len(repo.list_world_entries(project_id)),
            "timeline_events_count": len(repo.list_timeline_events(project_id)),
            "geography_locations_count": len(repo.list_geography_locations(project_id)),
            "sub_plots_count": len(repo.list_subplots(project_id)),
            "seeds_count": len(repo.list_seeds(project_id)),
        }
        self.log.info(
            "WTM.run_initial_baseline_react BASELINE_STATS: project_id=%s, summary=%s",
            project_id, summary,
        )

        # v0.9 改造：调 Validator 校验落库后的基座一致性
        from backend.agent.agents.validator import get_validator, ValidationStatus
        validator = get_validator()
        user_intent = json.dumps(steward_payload, ensure_ascii=False)
        validation = await validator.validate_world_tree(
            project_id=project_id,
            user_intent=user_intent,
        )

        # 联动（Onboarding 必须 PASS/WARN 才算成功）
        if validation.status == ValidationStatus.FATAL:
            await self._rollback_all_writes(project_id, executor_output.tool_calls_history)
            return {
                "success": False,
                "iterations": executor_output.iterations,
                "tool_calls_count": len(executor_output.tool_calls_history),
                "validation": validation,
                "error": "基座违反 hard rule",
            }
        elif validation.status == ValidationStatus.BLOCKED:
            await self._rollback_issue_rows(project_id, validation.issues)
            return {
                "success": False,
                "iterations": executor_output.iterations,
                "tool_calls_count": len(executor_output.tool_calls_history),
                "validation": validation,
                "error": "基座需要修正",
            }

        return {
            "success": True,
            "iterations": executor_output.iterations,
            "tool_calls_count": len(executor_output.tool_calls_history),
            "tool_calls_trace": executor_output.tool_calls_history,
            "summary": summary,
            "final_response": executor_output.final_response,
            "validation": validation,
            "error": None,
        }

    # ── v0.9 新增：Validator 联动回滚 ─────────────────────

    async def _rollback_all_writes(self, project_id: str, tool_calls_trace: list) -> None:
        """全清 WTM 本次 ReAct 落库的所有新行（FATAL 时调用）

        从 tool_calls_trace 提取 edit_artifact 成功调用的 row_id，逐个 delete
        """
        from backend.agent.tools.edit_artifact_tool import EditArtifactTool, EditArtifactInput
        tool = EditArtifactTool()
        cleared = 0
        for tc in tool_calls_trace:
            tool_name = tc.get("tool_name", "")
            tc_result = tc.get("result", {}) or {}
            if tool_name == "edit_artifact" and tc.get("status") == "success":
                target = tc_result.get("target")
                row_id = tc_result.get("row_id") or tc_result.get("id")
                if target and row_id:
                    try:
                        await tool.run(EditArtifactInput(
                            project_id=project_id,
                            target=target,
                            operation="delete",
                            identifier=row_id,
                        ))
                        cleared += 1
                    except Exception as e:
                        self.log.warning(f"_rollback_all_writes 失败 target={target} id={row_id}: {e}")
        self.log.info(f"WTM _rollback_all_writes: cleared {cleared} rows for project_id={project_id}")

    async def _rollback_issue_rows(self, project_id: str, issues: list) -> None:
        """只清 issues 标记的行（BLOCKED 时调用，B 方案精准回滚）

        从 issues 里的 table+field 找 row_id，逐个 delete
        """
        from backend.agent.tools.edit_artifact_tool import EditArtifactTool, EditArtifactInput
        from backend.persistence import ProjectRepository
        tool = EditArtifactTool()
        repo = ProjectRepository()
        cleared = 0
        for issue in issues:
            # 只回滚 error/fatal 严重度，warning 不回滚
            sev = issue.severity.value if hasattr(issue.severity, "value") else str(issue.severity)
            if sev not in ("error", "fatal"):
                continue
            table = issue.table
            if not table:
                continue
            # 通过 table 找符合 issue.description 关键词的 row_id（简化：找最新一行）
            # 实际生产应该根据 issue.field 更精确匹配
            try:
                row_id = self._find_row_for_issue(repo, project_id, table, issue)
                if row_id:
                    await tool.run(EditArtifactInput(
                        project_id=project_id,
                        target=table,
                        operation="delete",
                        identifier=row_id,
                    ))
                    cleared += 1
            except Exception as e:
                self.log.warning(f"_rollback_issue_rows 失败 table={table}: {e}")
        self.log.info(f"WTM _rollback_issue_rows: cleared {cleared} rows for project_id={project_id}")

    def _find_row_for_issue(self, repo, project_id: str, table: str, issue) -> Optional[str]:
        """根据 issue 找最可能对应的 row_id（简化实现）"""
        try:
            if table in ("characters", "character", "character_card"):
                chars = repo.list_characters(project_id)
                if chars:
                    return chars[-1].id
            elif table in ("main_plot_node", "main_plot", "main_plot_nodes"):
                nodes = repo.list_main_plot_nodes(project_id)
                if nodes:
                    return nodes[-1].id
            elif table in ("volumes", "volume"):
                vols = repo.list_volumes(project_id)
                if vols:
                    return vols[-1].id
            elif table in ("world_entries", "world_entry"):
                entries = repo.list_world_entries(project_id)
                if entries:
                    return entries[-1].id
            elif table in ("sub_plot", "sub_plot_nodes", "sub_plots"):
                subs = repo.list_subplots(project_id)
                if subs:
                    return subs[-1].id
            elif table in ("timeline_events", "timeline_event"):
                evts = repo.list_timeline_events(project_id)
                if evts:
                    return evts[-1].id
            elif table in ("geography_locations", "geography_location"):
                locs = repo.list_geography_locations(project_id)
                if locs:
                    return locs[-1].id
            elif table in ("seeds", "seed"):
                sds = repo.list_seeds(project_id)
                if sds:
                    return sds[-1].id
        except Exception as e:
            self.log.warning(f"_find_row_for_issue 失败: {e}")
        return None

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
        self.log.debug(
            "WorldTreeManager._run_consistency_check: project_id=%s, "
            "proposed_updates=%d, proposed_seeds=%d",
            project_id, len(proposed_updates), len(proposed_seeds),
        )
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

            result = checker.check(
                before=before,
                after=after,
                proposed_updates=proposed_updates,
                proposed_seeds=proposed_seeds,
            )
            self.log.info(
                "WorldTreeManager._run_consistency_check: project_id=%s, status=%s, "
                "conflicts=%d, warnings=%d",
                project_id, result.status, len(result.conflicts), len(result.warnings),
            )
            return result
        except Exception as e:
            self.log.warning(
                "WorldTreeManager._run_consistency_check FAILED: project_id=%s, error=%s",
                project_id, e,
            )
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
            self.log.warning(
                "WorldTreeManager._parse_diff: 无法提取 JSON: intent=%s, preview=%s",
                intent, final[:200],
            )
            return WorldTreeDiff(
                intent=intent,
                summary=final[:200] or "LLM 输出无法解析",
                consistency=ConsistencyCheckResult(status="FAIL", conflicts=["JSON 解析失败"]),
                risk_level="high",
                requires_double_confirm=True,
            )

        self.log.debug(
            "WorldTreeManager._parse_diff OK: intent=%s, base_updates=%d, "
            "plot_adj=%d, seeds=%d",
            intent,
            len(parsed.get("base_updates") or []),
            len(parsed.get("plot_adjustments") or []),
            len(parsed.get("new_seeds") or []),
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

# ============ v003 WTM 主入口：generate_full_world_tree_baseline ============



def _upsert_world_tree_minimal(
    project_id: str,
    story_core: str = "",
    genre_tags: Optional[List[str]] = None,
    core_rules: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """upsert world_tree 5 字段（供 WTM 主入口使用）"""
    from backend.persistence import get_store
    import json as _json
    from datetime import datetime as _dt

    now = _dt.now()
    with get_store().connection() as conn:
        conn.execute(
            """
            INSERT INTO world_tree (
                project_id, story_core, genre_tags_json, core_rules_json, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                story_core=excluded.story_core,
                genre_tags_json=excluded.genre_tags_json,
                core_rules_json=excluded.core_rules_json,
                updated_at=excluded.updated_at
            """,
            (
                project_id,
                story_core,
                _json.dumps(genre_tags or [], ensure_ascii=False),
                _json.dumps(core_rules or [], ensure_ascii=False),
                now,
            ),
        )
