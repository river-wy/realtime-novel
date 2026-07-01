"""onboarding_tools — Onboarding 管家 WTM 委托工具（v003）

v003 委托模式（spec §5.8）：
- 删 v0.7 旧 5 步工具（onboarding_propose_step / onboarding_user_confirm / onboarding_generate_chapter）
  —— 2026-07-01 完整删除
- 管家在 ReAct loop 多轮对话中自由收集用户信息（不限步数）
- 信息足够（spec §5.6 6 项通过）后调 delegate_to_wtm 委托 WTM 输出完整世界树基座（9 张表）
- 委托前后可调 verify_world_tree_baseline 校验基座完整性
- 委托成功后会触发 onboarding.step4_confirmed 事件（生成项目名 + 封面图）
  —— 事件定义保留，emit 源从 onboarding_user_confirm 迁到 delegate_to_wtm 成功路径
"""
from __future__ import annotations

import logging
from pydantic import BaseModel, Field
from typing import Optional, Any, List

from backend.agent.tools.base import BaseTool, register_tool

log = logging.getLogger(__name__)


# ============ Schemas ============

class DelegateToWTMInput(BaseModel):
    """管家委托 WTM 工具的输入

    v003 spec §5.8.4：管家收集足够信息后调此工具委托 WTM Agent 输出完整世界树基座。
    steward_payload 是 free-form 字典，包含管家从用户对话中提炼出的所有信息提示。
    """
    project_id: str = Field(..., description="项目 ID")
    steward_payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="管家从用户对话中提炼的信息提示（story_core_hint / characters_hint / world_setting_hint / core_rules_hint / style_hint 等）",
    )


class DelegateToWTMOutput(BaseModel):
    """委托 WTM 工具的输出"""
    success: bool
    world_tree_set: bool = False
    characters_count: int = 0
    main_plot_nodes_count: int = 0
    volumes_count: int = 0
    world_entries_count: int = 0
    timeline_events_count: int = 0
    geography_locations_count: int = 0
    sub_plots_count: int = 0
    seeds_count: int = 0
    error: Optional[str] = None


class VerifyWorldTreeBaselineInput(BaseModel):
    """世界树基座完整性校验工具的输入"""
    project_id: str = Field(..., description="项目 ID")


class VerifyWorldTreeBaselineOutput(BaseModel):
    """世界树基座完整性校验工具的输出"""
    ready: bool
    missing_items: List[str] = Field(default_factory=list)
    all_items: List[str] = Field(default_factory=list)


# ============ Tools ============

class DelegateToWTMTool(BaseTool):
    """管家委托 WTM Agent 输出完整世界树基座（v003 spec §5.8.2）

    管家判断"信息足够"后调此工具（spec §5.6 6 项全部通过即满足），委托 WTM Agent
    输出完整世界树基座（9 张表：world_tree + characters + main_plot + sub_plot + volumes
    + world_entries + timeline_events + geography_locations + core_rules_json）。

    调用流程：
    1. onboarding_state.info_state → 'wtm_pending'
    2. WTM Agent 生成世界树基座并落库
    3. 成功：info_state → 'ready' + emit 'onboarding.step4_confirmed' 事件
       失败：info_state → 'collecting'（管家继续对话）
    """
    name = "delegate_to_wtm"
    description = (
        "管家收集到足够用户信息后，委托 WTM Agent 输出完整世界树基座（9 张表）。"
        "调用前提：spec §5.6 6 项校验（story_core/genre_tags/core_rules/protagonist/pending_node/volume）"
        "全部通过；不满足时管家应继续对话收集。"
    )
    input_schema = DelegateToWTMInput
    output_schema = DelegateToWTMOutput

    async def run(self, input: DelegateToWTMInput, progress_callback=None) -> DelegateToWTMOutput:
        try:
            from backend.services.onboarding_artifacts import delegate_to_wtm

            result = await delegate_to_wtm(
                project_id=input.project_id,
                steward_payload=input.steward_payload,
            )
            summary = result.get("summary", {}) or {}
            return DelegateToWTMOutput(
                success=result.get("success", False),
                world_tree_set=summary.get("world_tree_set", False),
                characters_count=summary.get("characters_count", 0),
                main_plot_nodes_count=summary.get("main_plot_nodes_count", 0),
                volumes_count=summary.get("volumes_count", 0),
                world_entries_count=summary.get("world_entries_count", 0),
                timeline_events_count=summary.get("timeline_events_count", 0),
                geography_locations_count=summary.get("geography_locations_count", 0),
                sub_plots_count=summary.get("sub_plots_count", 0),
                seeds_count=summary.get("seeds_count", 0),
                error=result.get("error"),
            )
        except Exception as e:
            log.error(f"delegate_to_wtm 工具失败: {e}", exc_info=True)
            return DelegateToWTMOutput(
                success=False,
                error=str(e),
            )


class VerifyWorldTreeBaselineTool(BaseTool):
    """校验世界树基座完整性（v003 spec §5.6 6 项）

    管家委托 WTM 前可先调此工具校验 6 项是否齐全；委托 WTM 后再调一次确认 ready。
    """
    name = "verify_world_tree_baseline"
    description = (
        "校验当前项目的世界树基座是否完整（spec §5.6 6 项）："
        "world_tree.story_core / genre_tags_json / core_rules_json / "
        "characters 至少 1 个 protagonist / main_plot 至少 1 个 pending 节点 / volumes 至少 1 个卷。"
    )
    input_schema = VerifyWorldTreeBaselineInput
    output_schema = VerifyWorldTreeBaselineOutput

    async def run(self, input: VerifyWorldTreeBaselineInput, progress_callback=None) -> VerifyWorldTreeBaselineOutput:
        try:
            from backend.services.onboarding_artifacts import verify_world_tree_baseline

            result = verify_world_tree_baseline(input.project_id)
            return VerifyWorldTreeBaselineOutput(
                ready=result.get("ready", False),
                missing_items=result.get("missing_items", []),
                all_items=result.get("all_items", []),
            )
        except Exception as e:
            log.error(f"verify_world_tree_baseline 工具失败: {e}", exc_info=True)
            return VerifyWorldTreeBaselineOutput(
                ready=False,
                missing_items=[f"校验异常: {e}"],
            )


# v003 工具注册
register_tool(DelegateToWTMTool())
register_tool(VerifyWorldTreeBaselineTool())
