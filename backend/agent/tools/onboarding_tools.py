"""onboarding_tools — Onboarding 基座完整性校验工具

合并后保留：
- delegate_to_wtm + delegate_to_agent：Onboarding 阶段委托 WTM 完整基座生成
  走 delegate_to_agent(agent="world_tree_manager", mode="full_baseline", payload=...)
- 本文件仅保留 verify_world_tree_baseline（边界清晰：这是校验工具，不是委托，
  不跟 delegate_to_agent 重复）

委托模式（spec §5.8）：
- 删旧 5 步工具（onboarding_propose_step / onboarding_user_confirm / onboarding_generate_chapter）
- 管家在 ReAct loop 多轮对话中自由收集用户信息（不限步数）
- 信息足够（spec §5.6 6 项通过）后调 verify_world_tree_baseline 校验
- 通过后调 delegate_to_agent(agent="world_tree_manager", mode="full_baseline", payload=...)
  委托 WTM 输出完整世界树基座（9 张表）
- 委托成功后会触发 onboarding.step4_confirmed 事件（生成项目名 + 封面图）
"""
from __future__ import annotations

import logging
from pydantic import BaseModel, Field
from typing import List

from backend.agent.tools.base import BaseTool, register_tool

log = logging.getLogger(__name__)


# ============ Schemas ============

class VerifyWorldTreeBaselineInput(BaseModel):
    """世界树基座完整性校验工具的输入"""
    project_id: str = Field(..., description="项目 ID")


class VerifyWorldTreeBaselineOutput(BaseModel):
    """世界树基座完整性校验工具的输出"""
    ready: bool
    missing_items: List[str] = Field(default_factory=list)
    all_items: List[str] = Field(default_factory=list)


# ============ Tools ============

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


# 注册
register_tool(VerifyWorldTreeBaselineTool())
