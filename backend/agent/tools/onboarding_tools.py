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
    # v0.6.2: Step 3/4 可选传 fields (管家 ReAct 装入设计后的字段); 为空则只记录 user_response
    fields: Optional[dict] = Field(
        default=None,
        description="Step 3/4 管家设计的字段 (Step 3: story_core/characters/opening_scene, Step 4: main_arc/sub_plots/seeds/reader_feeling)",
    )


class OnboardingUserConfirmOutput(BaseModel):
    step: int
    recorded: bool
    next_step: Optional[int] = None
    # v0.6.2: 附加信息 (Step 3/4 写 7 件后填)
    artifacts_written: Optional[list[str]] = Field(default=None, description="Step 3/4 写入的 7 件列表")
    step4_hook_emitted: Optional[bool] = Field(default=None, description="Step 4 后置 hook 是否 emit")


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
    """Onboarding 用户确认 (v0.6.2 吸收 WS handler 责任)

    v0.6.2 改造:
    - Step 1/2: 只写 user_response 到 payload
    - Step 3/4: 如果传 fields, 调 merge_payload_to_state + assemble_7_artifacts 写 7 件
    - Step 4 完成后: emit 'onboarding.step4_confirmed' 事件 (hooks.py 监听)

    设计意图: 管家 ReAct 调一次工具完成所有副作用, 工具是唯一副作用入口。
    """
    name = "onboarding_user_confirm"
    description = (
        "记录用户对当前 step 的确认/修改, 自动推进到下一步。"
        "Step 3/4 传 fields 时还会调 assemble_7_artifacts 写 7 件, "
        "Step 4 完成后会触发项目名+封面图生成后置钩子。"
    )
    input_schema = OnboardingUserConfirmInput
    output_schema = OnboardingUserConfirmOutput

    async def run(self, input: OnboardingUserConfirmInput, progress_callback=None) -> OnboardingUserConfirmOutput:
        try:
            from backend.services.onboarding_flow import OnboardingFlow
            flow = OnboardingFlow()
            step_str = str(input.step)

            # 1. 始终写 user_response 到 payload (记录对话)
            await flow.step(input.project_id, step_str, {"user_response": input.user_response})

            artifacts_written = None
            step4_hook_emitted = None

            # 2. Step 3/4: 写 7 件 + emit 后置事件
            if input.step in (3, 4) and input.fields:
                from backend.services.onboarding_artifacts import (
                    assemble_7_artifacts,
                    merge_payload_to_state,
                    load_payload,
                )
                # 2a. 合并 fields 到 state_json.payload
                merge_payload_to_state(input.project_id, input.step, input.fields)
                # 2b. 拼装 7 件
                payload_full = load_payload(input.project_id)
                artifacts_written = assemble_7_artifacts(input.project_id, payload_full)
                log.info(
                    "onboarding_user_confirm: project_id=%s, step=%d, "
                    "artifacts_written=%s",
                    input.project_id, input.step, artifacts_written,
                )

                # 2c. Step 4 完成后 emit 后置事件 (项目名 + 封面图生成)
                if input.step == 4:
                    try:
                        from backend.core.event_bus import event_bus
                        await event_bus.emit(
                            "onboarding.step4_confirmed",
                            project_id=input.project_id,
                            payload=payload_full,
                            ws=None,  # 管家路径不传 ws, 后置任务异步生成后推 WS
                        )
                        step4_hook_emitted = True
                        log.info(
                            "onboarding_user_confirm: emit onboarding.step4_confirmed "
                            "for project_id=%s",
                            input.project_id,
                        )
                    except Exception as e:
                        log.warning(
                            "onboarding_user_confirm: step4 hook emit failed: %s",
                            str(e),
                        )
                        step4_hook_emitted = False

            return OnboardingUserConfirmOutput(
                step=input.step,
                recorded=True,
                next_step=input.step + 1 if input.step < 5 else None,
                artifacts_written=artifacts_written,
                step4_hook_emitted=step4_hook_emitted,
            )
        except Exception as e:
            log.error(f"onboarding_user_confirm 失败: {e}", exc_info=True)
            return ToolError(code="CONFIRM_FAILED", message=str(e))


class OnboardingGenerateChapterTool(BaseTool):
    """Onboarding Step 5 生成第 1 章（v0.6.2 委托文笔家 ReAct）"""
    name = "onboarding_generate_chapter"
    description = "Step 5: 委托文笔家生成第 1 章（60-100s，真 LLM 调用，ReAct loop 调 generate_chapter / summarize_chapter 工具）"
    input_schema = OnboardingGenerateChapterInput
    output_schema = OnboardingGenerateChapterOutput

    async def run(self, input: OnboardingGenerateChapterInput, progress_callback=None) -> OnboardingGenerateChapterOutput:
        try:
            from backend.agent.agents.novel_writer import delegate_chapter_generation
            from backend.persistence import ProjectRepository

            chapter_output = await delegate_chapter_generation(
                project_id=input.project_id,
                intervention=None,
                source="onboarding_step5",
            )
            if chapter_output.error:
                return ToolError(code="GENERATE_FAILED", message=chapter_output.error)

            project = ProjectRepository().get(input.project_id)
            return OnboardingGenerateChapterOutput(
                chapter_num=chapter_output.chapter_num or 0,
                title=chapter_output.title or "",
                word_count=chapter_output.word_count or len(chapter_output.chapter_content),
                summary=chapter_output.chapter_summary or "",
                project_name=project.name if project else "",
            )
        except Exception as e:
            log.error(f"onboarding_generate_chapter 失败: {e}", exc_info=True)
            return ToolError(code="GENERATE_FAILED", message=str(e))


# 注册
register_tool(OnboardingProposeStepTool())
register_tool(OnboardingUserConfirmTool())
register_tool(OnboardingGenerateChapterTool())
