"""onboarding_tools — Onboarding 推进工具

管家在 ReAct loop 里调这些工具完成 5 步 Onboarding:
- onboarding_propose_step: Step 1/2 单次 LLM 推演；Step 3 委托 WTM 初始化 7 件基座；Step 4 读回大纲字段
- onboarding_user_confirm: 记录用户确认；Step 3/4 若 WTM 已落盘则只合并 payload（降级时用 assemble_7_artifacts 兜底）；Step 4 emit 后置钩子
- onboarding_generate_chapter: Step 5 委托文笔家生成第 1 章
"""
from __future__ import annotations

import json
import logging
from pydantic import BaseModel, Field
from typing import Optional, Any, List

from backend.agent.tools.base import BaseTool, ToolError, register_tool

log = logging.getLogger(__name__)


# ============ Input/Output Schemas ============

class OnboardingProposeStepInput(BaseModel):
    project_id: str = Field(..., description="项目 ID")
    step: int = Field(..., ge=1, le=5, description="Onboarding 步数 (1-5)")
    user_response: Optional[str] = Field(default="", description="用户对此步的反馈/补充 (可选)")


class OnboardingProposeStepOutput(BaseModel):
    step: int
    proposed_fields: dict = Field(
        default_factory=dict,
        description="LLM 提议的字段（Step 1: {genres,styles,tone}, Step 2: {palette}, Step 3: {story_core,characters,opening_scene}, Step 4: {main_arc,sub_plots,seeds}）",
    )
    expected_user_input_hint: str = Field(default="", description="Step 3/4 专用：管家告诉用户下一步期望输入什么")


class OnboardingUserConfirmInput(BaseModel):
    project_id: str
    step: int = Field(..., ge=1, le=5)
    user_response: str = Field(..., description="用户对 step 的响应 (确认/修改/补充)")
    # v0.6.2: Step 3/4 可选传 fields (管家 ReAct 装入设计后的字段); 为空则只记录 user_response
    fields: Optional[dict] = Field(
        default=None,
        description="Step 3/4 管家设计的字段（Step 3: story_core/characters/opening_scene，Step 4: main_arc/sub_plots/seeds）",
    )


class OnboardingUserConfirmOutput(BaseModel):
    step: int
    recorded: bool
    next_step: Optional[int] = None
    artifacts_written: Optional[List[str]] = Field(default=None, description="Step 3/4 写入的 7 件列表")
    step4_hook_emitted: Optional[bool] = Field(default=None, description="Step 4 后置 hook 是否触发")


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
    """Onboarding 步骤提议 (Step 1-4)

    Step 1/2: 单次 LLM 推演（题材/风格/基调、palette）
    Step 3:   委托 WorldTreeManager.initialize_world_tree()，一次性完成 7 件基座设计+落盘
              （合并了原 step 3+4 的推演，WTM 用自己的 ReAct loop + edit_artifact 工具写库）
    Step 4:   从 DB 读回 WTM 已写入的大纲字段（main_arc/sub_plots/seeds）回传给管家展示
              （不再重复推演，只是给管家和用户一个确认界面）
    """
    name = "onboarding_propose_step"
    description = (
        "Onboarding 5 步: 调 LLM 提议某步的字段 (Step 1-4).\n"
        "Step 1/2 直接推演字段;\n"
        "Step 3 委托 WorldTreeManager 一次性初始化完整 7 件基座（含大纲，耗时较长）;\n"
        "Step 4 读回 Step 3 已生成的大纲字段供用户确认（不重复推演）."
    )
    input_schema = OnboardingProposeStepInput
    output_schema = OnboardingProposeStepOutput

    async def run(self, input: OnboardingProposeStepInput, progress_callback=None) -> OnboardingProposeStepOutput:
        try:
            from backend.services.onboarding_flow import OnboardingFlow

            # 1. 拿当前 onboarding_state
            flow = OnboardingFlow()
            state = await flow.load_state(input.project_id)
            if not state:
                return ToolError(code="STATE_NOT_FOUND", message=f"onboarding_state 不存在: project_id={input.project_id}")

            payload = state.get("payload", {}) or {}

            # ── Step 1/2：单次 LLM 推演（保持原逻辑）────────────────────────────
            if input.step in (1, 2):
                from backend.agent.onboarding.controller import get_onboarding_controller
                controller = get_onboarding_controller()
                result = await controller.consult(
                    project_id=input.project_id,
                    step=input.step,
                    user_message=input.user_response or f"提议 Step {input.step} 字段",
                    current_fields=payload,
                )
                if result.error:
                    return ToolError(code="CONSULT_FAILED", message=result.error)
                return OnboardingProposeStepOutput(
                    step=input.step,
                    proposed_fields=result.fields or {},
                    expected_user_input_hint="",
                )

            # ── Step 3：委托 WorldTreeManager 初始化 7 件基座 ──────────────────────
            elif input.step == 3:
                log.info(
                    "onboarding_propose_step step=3: 委托 WorldTreeManager.initialize_world_tree, "
                    "project_id=%s, payload_keys=%s",
                    input.project_id, list(payload.keys()),
                )

                # user_response 可能包含用户对故事/角色的补充描述，合并进 payload
                enriched_payload = dict(payload)
                if input.user_response:
                    enriched_payload["extra_user_notes"] = input.user_response

                from backend.agent.agents.world_tree_manager import get_world_tree_manager
                manager = get_world_tree_manager()
                diff = await manager.initialize_world_tree(
                    project_id=input.project_id,
                    onboarding_payload=enriched_payload,
                )

                log.info(
                    "onboarding_propose_step step=3 WTM DONE: project_id=%s, "
                    "base_updates=%d, new_seeds=%d, error_hint=%s",
                    input.project_id,
                    len(diff.base_updates), len(diff.new_seeds),
                    diff.consistency.status,
                )

                # 把 WTM 写入结果摘要回传给管家（供 onboarding_user_confirm step=3 记录）
                proposed = {
                    "wtm_initialized": True,
                    "summary": diff.summary,
                    "base_updates_count": len(diff.base_updates),
                    "new_seeds_count": len(diff.new_seeds),
                    "consistency_status": diff.consistency.status,
                    "iterations": diff.iterations,
                    # 透传核心字段，供管家展示摘要给用户
                    "story_core": payload.get("story_core", ""),
                    "characters": payload.get("characters", ""),
                    "opening_scene": payload.get("opening_scene", ""),
                }

                return OnboardingProposeStepOutput(
                    step=input.step,
                    proposed_fields=proposed,
                    expected_user_input_hint=(
                        "世界树已初始化完毕。以上是故事核心和角色设定，"
                        "如没问题请确认，或告诉我需要调整的地方。"
                    ),
                )

            # ── Step 4：读回 WTM 已写入的大纲字段（不重复推演）──────────────────
            elif input.step == 4:
                log.info(
                    "onboarding_propose_step step=4: 读回 WTM 已写入的大纲字段, project_id=%s",
                    input.project_id,
                )
                # 从 DB 直接读 main_plot / sub_plot / seed_table
                try:
                    from backend.persistence import ProjectRepository
                    repo = ProjectRepository()
                    artifacts = repo.load_all_artifacts(input.project_id)
                    main_plot = artifacts.get("main_plot", {})
                    sub_plot = artifacts.get("sub_plot", {})
                    seed_table = artifacts.get("seed_table", {})

                    proposed = {
                        "main_arc": main_plot.get("arc_phrase", "") or "",
                        "beats": main_plot.get("beats", []),
                        "sub_plots": [t.get("summary", "") for t in (sub_plot.get("threads") or [])],
                        "seeds": [s.get("content", "") for s in (seed_table.get("seeds") or [])],
                    }
                except Exception as e:
                    log.warning(
                        "onboarding_propose_step step=4: 读取大纲字段失败 project_id=%s: %s",
                        input.project_id, e,
                    )
                    proposed = {"note": "大纲已由世界树管家初始化，读取详情失败，请继续确认"}

                return OnboardingProposeStepOutput(
                    step=input.step,
                    proposed_fields=proposed,
                    expected_user_input_hint=(
                        "以上是完整的主线大纲、支线和伏笔。"
                        "如没问题请确认，或告诉我需要调整的地方。"
                    ),
                )

            elif input.step == 5:
                return ToolError(code="WRONG_TOOL", message="Step 5 调 onboarding_generate_chapter, 不是 onboarding_propose_step")
            else:
                return ToolError(code="INVALID_STEP", message=f"step 必须是 1-5, 收到 {input.step}")

        except Exception as e:
            log.error(f"onboarding_propose_step 失败: {e}", exc_info=True)
            return ToolError(code="PROPOSE_FAILED", message=str(e))


class OnboardingUserConfirmTool(BaseTool):
    """Onboarding 用户确认

    - Step 1/2：只记录 user_response 到 payload
    - Step 3：若 fields 含 wtm_initialized=True，说明 WTM 已落盘，只 merge payload；否则降级到 assemble_7_artifacts
    - Step 4：同 Step 3 逻辑；完成后无论哪条路径都 emit 'onboarding.step4_confirmed'
    - Step 4 后置：hooks.py 监听，异步生成项目名 + 封面图
    """
    name = "onboarding_user_confirm"
    description = (
        "记录用户对当前 step 的确认/修改，自动推进到下一步。"
        "Step 3/4 若 WTM 已完成初始化（fields.wtm_initialized=True），只合并 payload；"
        "否则降级调 assemble_7_artifacts 兜底写 7 件基座。"
        "Step 4 完成后触发项目名+封面图生成钩子。"
    )
    input_schema = OnboardingUserConfirmInput
    output_schema = OnboardingUserConfirmOutput

    async def run(self, input: OnboardingUserConfirmInput, progress_callback=None) -> OnboardingUserConfirmOutput:
        try:
            from backend.services.onboarding_flow import OnboardingFlow
            flow = OnboardingFlow()
            step_str = str(input.step)

            # 记录 user_response 到 state payload
            await flow.step(input.project_id, step_str, {"user_response": input.user_response})

            artifacts_written = None
            step4_hook_emitted = None

            if input.step in (3, 4) and input.fields:
                from backend.services.onboarding_artifacts import (
                    merge_payload_to_state,
                    load_payload,
                )

                # Step 3：WTM 已通过 initialize_world_tree() 完成 7 件基座写库
                # 判断依据：fields 里含 wtm_initialized=True
                wtm_initialized = bool(input.fields.get("wtm_initialized"))

                if input.step == 3:
                    if wtm_initialized:
                        # 主路径：WTM 已落盘，只需把核心字段合并进 state payload 供后续读取
                        merge_payload_to_state(input.project_id, input.step, input.fields)
                        artifacts_written = ["wtm_initialized"]  # 标记，非真实写入列表
                        log.info(
                            "onboarding_user_confirm step=3: WTM 已初始化，跳过 assemble_7_artifacts, "
                            "project_id=%s",
                            input.project_id,
                        )
                    else:
                        # 降级路径：WTM 初始化失败，回退到 assemble_7_artifacts 机械拼装
                        from backend.services.onboarding_artifacts import assemble_7_artifacts
                        log.warning(
                            "onboarding_user_confirm step=3: wtm_initialized 缺失，降级到 assemble_7_artifacts, "
                            "project_id=%s",
                            input.project_id,
                        )
                        merge_payload_to_state(input.project_id, input.step, input.fields)
                        payload_full = load_payload(input.project_id)
                        artifacts_written = assemble_7_artifacts(input.project_id, payload_full)
                        log.info(
                            "onboarding_user_confirm step=3 fallback: artifacts_written=%s, project_id=%s",
                            artifacts_written, input.project_id,
                        )

                elif input.step == 4:
                    if wtm_initialized:
                        # 主路径：大纲已在 step=3 时由 WTM 写入，只记录确认状态
                        merge_payload_to_state(input.project_id, input.step, input.fields)
                        artifacts_written = ["wtm_initialized"]
                        log.info(
                            "onboarding_user_confirm step=4: WTM 已初始化，跳过 assemble, "
                            "project_id=%s",
                            input.project_id,
                        )
                    else:
                        # 降级路径：step=3 时未走 WTM，在 step=4 补做 assemble（兜底）
                        from backend.services.onboarding_artifacts import assemble_7_artifacts
                        log.warning(
                            "onboarding_user_confirm step=4: wtm_initialized 缺失，降级到 assemble_7_artifacts, "
                            "project_id=%s",
                            input.project_id,
                        )
                        merge_payload_to_state(input.project_id, input.step, input.fields)
                        payload_full = load_payload(input.project_id)
                        artifacts_written = assemble_7_artifacts(input.project_id, payload_full)

                    # Step 4 无论哪条路径都 emit 后置事件（触发项目名自动生成 + 封面）
                    try:
                        payload_full = load_payload(input.project_id)
                        from backend.core.event_bus import event_bus
                        await event_bus.emit(
                            "onboarding.step4_confirmed",
                            project_id=input.project_id,
                            payload=payload_full,
                            ws=None,
                        )
                        step4_hook_emitted = True
                        log.info(
                            "onboarding_user_confirm: emit onboarding.step4_confirmed, project_id=%s",
                            input.project_id,
                        )
                    except Exception as e:
                        log.warning("onboarding_user_confirm: step4 hook emit failed: %s", str(e))
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
    """Onboarding Step 5：委托文笔家 ReAct loop 生成第 1 章"""
    name = "onboarding_generate_chapter"
    description = "Step 5：委托文笔家生成第 1 章（60-100s，ReAct loop 调 generate_chapter / summarize_chapter 工具落盘）"
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
