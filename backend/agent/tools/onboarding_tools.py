"""Onboarding 推进工具 (v0.6.1)

管家在 ReAct loop 里调这些工具, 自己一步步推 5 步 Onboarding:
- onboarding_propose_step: 调 LLM 提议某步的字段 (Step 1-4)
- onboarding_user_confirm: 记录用户对某步的确认/修改
- onboarding_generate_chapter: Step 5 调 specialist 生成第 1 章

onboarding_start **不复用 create_project**, 因为 Onboarding 流程的「创建项目」时机是管家自己决定的 (用户先说「我想写」管家再调 onboarding_start)。
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Any
from pydantic import BaseModel, Field

from backend.agent.tools.base import BaseTool, ToolError, register_tool
from backend.agent.tools.schemas import ProjectDetail

log = logging.getLogger(__name__)


# ============ Input/Output Schemas ============

class OnboardingProposeStepInput(BaseModel):
    project_id: str = Field(..., description="项目 ID")
    step: int = Field(..., ge=1, le=5, description="Onboarding 步数 (1-5)")
    user_response: Optional[str] = Field(default="", description="用户对此步的反馈/补充 (可选)")


class OnboardingProposeStepOutput(BaseModel):
    step: int
    proposed_fields: dict = Field(default_factory=dict, description="LLM 提议的字段 (Step 1: {genres,styles,tone}, Step 2: {palette}, Step 3: {story_core,characters,opening_scene}, Step 4: {main_arc,sub_plots,seeds,reader_feeling})")
    expected_user_input_hint: str = Field(default="", description="管家告诉用户「下一步期望用户输入什么」(Step 3/4 专用)")


class OnboardingUserConfirmInput(BaseModel):
    project_id: str
    step: int = Field(..., ge=1, le=5)
    user_response: str = Field(..., description="用户对 step 的响应 (确认/修改/补充)")


class OnboardingUserConfirmOutput(BaseModel):
    step: int
    recorded: bool
    next_step: Optional[int] = None


class OnboardingGenerateChapterInput(BaseModel):
    project_id: str


class OnboardingGenerateChapterOutput(BaseModel):
    chapter_num: int
    title: str
    word_count: int
    summary: str = ""
    project_name: str = ""


# ============ Tools ============

class OnboardingProposeStepTool(BaseTool):
    """Onboarding 步骤提议 (Step 1-4)"""
    name = "onboarding_propose_step"
    description = "Onboarding 5 步: 调 LLM 提议某步的字段 (Step 1-4). Step 1/2 直接返回字段, Step 3/4 还会返回 expected_user_input_hint 告诉用户「下一步应该输入什么」"
    input_schema = OnboardingProposeStepInput
    output_schema = OnboardingProposeStepOutput

    async def run(self, input: OnboardingProposeStepInput, progress_callback=None) -> OnboardingProposeStepOutput:
        try:
            from backend.agent.onboarding.controller import get_onboarding_controller
            from backend.services.onboarding_flow import OnboardingFlow

            # 1. 拿当前 onboarding_state
            flow = OnboardingFlow()
            state = await flow.load_state(input.project_id)
            if not state:
                return ToolError(code="STATE_NOT_FOUND", message=f"onboarding_state 不存在: project_id={input.project_id}")

            # 2. Step 1/2/3/4 各自处理
            if input.step in (1, 2, 3, 4):
                # 1-2: 单轮 LLM 推演 (从已有 payload 推断)
                # 3-4: 调 controller.consult() 多轮推演
                controller = get_onboarding_controller()
                result = await controller.consult(
                    project_id=input.project_id,
                    step=input.step,
                    user_message=input.user_response or f"提议 Step {input.step} 字段",
                    current_fields=state.get("payload", {}),
                )
                if result.error:
                    return ToolError(code="CONSULT_FAILED", message=result.error)
                proposed = result.fields or {}
            elif input.step == 5:
                return ToolError(code="WRONG_TOOL", message="Step 5 调 onboarding_generate_chapter, 不是 onboarding_propose_step")
            else:
                return ToolError(code="INVALID_STEP", message=f"step 必须是 1-5, 收到 {input.step}")

            # 3. Step 3/4 给 expected_user_input_hint
            hint = ""
            if input.step == 3:
                hint = "请告诉我你的主角是谁？他/她要面对什么冲突？或者直接说'差不多'，我帮你提议。"
            elif input.step == 4:
                hint = "请补充你希望的主线节点 (3-5 个) / 支线 / 伏笔，或者直接说'差不多了'，我帮你提议。"

            return OnboardingProposeStepOutput(
                step=input.step,
                proposed_fields=proposed,
                expected_user_input_hint=hint,
            )
        except Exception as e:
            log.error(f"onboarding_propose_step 失败: {e}", exc_info=True)
            return ToolError(code="PROPOSE_FAILED", message=str(e))


class OnboardingUserConfirmTool(BaseTool):
    """Onboarding 用户确认"""
    name = "onboarding_user_confirm"
    description = "记录用户对当前 step 的确认/修改, 并把 user_response 合并到 onboarding_state.payload, 自动推进到下一步"
    input_schema = OnboardingUserConfirmInput
    output_schema = OnboardingUserConfirmOutput

    async def run(self, input: OnboardingUserConfirmInput, progress_callback=None) -> OnboardingUserConfirmOutput:
        try:
            from backend.services.onboarding_flow import OnboardingFlow
            flow = OnboardingFlow()
            # step 字符串 (1-5)
            step_str = str(input.step)
            # 调 flow.step() 写 user_response 到 payload
            await flow.step(input.project_id, step_str, {"user_response": input.user_response})
            return OnboardingUserConfirmOutput(
                step=input.step,
                recorded=True,
                next_step=input.step + 1 if input.step < 5 else None,
            )
        except Exception as e:
            log.error(f"onboarding_user_confirm 失败: {e}", exc_info=True)
            return ToolError(code="CONFIRM_FAILED", message=str(e))


class OnboardingGenerateChapterTool(BaseTool):
    """Onboarding Step 5 生成第 1 章"""
    name = "onboarding_generate_chapter"
    description = "Step 5: 调 specialist 生成第 1 章 (60-100s, 真 LLM 调用)"
    input_schema = OnboardingGenerateChapterInput
    output_schema = OnboardingGenerateChapterOutput

    async def run(self, input: OnboardingGenerateChapterInput, progress_callback=None) -> OnboardingGenerateChapterOutput:
        try:
            from backend.agent.specialists.specialists import generate_chapter_via_specialist
            from backend.persistence import ProjectRepository

            chapter = await generate_chapter_via_specialist(project_id=input.project_id)
            project = ProjectRepository().get(input.project_id)
            return OnboardingGenerateChapterOutput(
                chapter_num=chapter.get("num", 0),
                title=chapter.get("title", ""),
                word_count=chapter.get("word_count", 0),
                summary=chapter.get("summary", ""),
                project_name=project.name if project else "",
            )
        except Exception as e:
            log.error(f"onboarding_generate_chapter 失败: {e}", exc_info=True)
            return ToolError(code="GENERATE_FAILED", message=str(e))


# 注册
register_tool(OnboardingProposeStepTool())
register_tool(OnboardingUserConfirmTool())
register_tool(OnboardingGenerateChapterTool())
