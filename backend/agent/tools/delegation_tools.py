"""delegation_tools — 专家 Agent 委托工具

两种委托语义：

1. DelegateToAgentTool（同步委托）
   - 管家 ReAct loop 挂起等待专家完成
   - 适用：用户明确等待的操作（生成章节、干预基座）
   - 结果注入管家 messages，管家继续推演后回复用户

2. DispatchBackgroundTaskTool（异步委托 / fire-and-forget）
   - 管家立即拿到 task_id 继续推演，专家在后台跑
   - 适用：管家自主识别的维护任务（更新 summary / 生成封面等）
   - 结果通过 EventBus → WS push 到前端

判断原则（写在 STEWARD_SYSTEM_PROMPT 里）：
  「用户在等这个结果吗？」是 → delegate_to_agent / 否 → dispatch_background_task
"""
from __future__ import annotations

import logging
import uuid
from pydantic import BaseModel, Field
from typing import Any, Optional

from backend.agent.tools.base import BaseTool, register_tool

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════
#  公共 Input/Output Schema
# ══════════════════════════════════════════════════════

class DelegateToAgentInput(BaseModel):
    agent: str = Field(
        ...,
        description=(
            "目标专家 Agent 名，可选值：\n"
            "- novel_writer：生成章节正文\n"
            "- world_tree_manager：分析干预 / 调整基座"
        ),
    )
    task: str = Field(
        ...,
        description="任务描述（自然语言，管家转述给专家的完整上下文，含用户原意）",
    )
    project_id: str = Field(..., description="项目 ID")


class DelegateToAgentOutput(BaseModel):
    agent: str
    success: bool
    result: str = Field(description="专家给管家看的一句话摘要")
    structured_data: dict = Field(default_factory=dict, description="专家返回的结构化数据")
    iterations: int = 0
    error: Optional[str] = None


class DispatchBackgroundTaskInput(BaseModel):
    agent: str = Field(
        ...,
        description=(
            "目标专家 Agent 名，可选值：\n"
            "- novel_writer：后台更新章节 summary\n"
            "- world_tree_manager：后台维护基座索引\n"
            "- image_generator：后台生成封面/插图"
        ),
    )
    task: str = Field(..., description="任务描述（管家转述）")
    project_id: str = Field(..., description="项目 ID")
    task_type: str = Field(
        ...,
        description=(
            "任务类型标识，前端可用来订阅 WS push，例如：\n"
            "update_chapter_summary / generate_cover / rebuild_memory_index"
        ),
    )


class DispatchBackgroundTaskOutput(BaseModel):
    task_id: str = Field(description="后台任务 ID，前端订阅 WS push 时使用")
    queued: bool
    message: str = Field(description="给管家看的提示，说明任务已派发")


# ══════════════════════════════════════════════════════
#  Tool 1：DelegateToAgentTool（同步委托）
# ══════════════════════════════════════════════════════

class DelegateToAgentTool(BaseTool):
    """同步委托专家 Agent 完成任务，管家等待结果后继续推演。

    适用场景（用户明确等待）：
    - 「继续写」/ 「生成下一章」→ novel_writer
    - 「把师父改成反派」/ 「调整主线」→ world_tree_manager
    """

    name = "delegate_to_agent"
    description = (
        "把任务同步委托给专家 Agent，等待结果后整合回复用户。\n"
        "适用于用户明确等待的操作（生成章节、干预基座）。\n"
        "agent 可选值：novel_writer / world_tree_manager"
    )
    input_schema = DelegateToAgentInput
    output_schema = DelegateToAgentOutput

    async def run(
        self,
        input: DelegateToAgentInput,
        progress_callback=None,
    ) -> DelegateToAgentOutput:
        log.info(
            "DelegateToAgentTool.run: agent=%s, project_id=%s, task_len=%d",
            input.agent, input.project_id, len(input.task),
        )

        try:
            if input.agent == "novel_writer":
                return await self._delegate_novel_writer(input)
            elif input.agent == "world_tree_manager":
                return await self._delegate_world_tree_manager(input)
            else:
                log.warning("DelegateToAgentTool: 未知 agent '%s'", input.agent)
                return DelegateToAgentOutput(
                    agent=input.agent,
                    success=False,
                    result="",
                    error=f"未知专家 Agent: {input.agent}，可选值: novel_writer / world_tree_manager",
                )
        except Exception as e:
            log.error(
                "DelegateToAgentTool.run FAILED: agent=%s, error=%s",
                input.agent, e, exc_info=True,
            )
            return DelegateToAgentOutput(
                agent=input.agent,
                success=False,
                result="",
                error=str(e),
            )

    # ── 各专家路由 ──────────────────────────────────────

    async def _delegate_novel_writer(
        self, input: DelegateToAgentInput
    ) -> DelegateToAgentOutput:
        """委托文笔家生成章节"""
        from backend.agent.agents.novel_writer import get_novel_writer

        writer = get_novel_writer()
        output = await writer.generate_chapter(
            project_id=input.project_id,
            user_message=input.task,
        )

        log.info(
            "DelegateToAgentTool._delegate_novel_writer DONE: "
            "project_id=%s, content_len=%d, iterations=%d, error=%s",
            input.project_id,
            len(output.chapter_content),
            output.iterations,
            output.error,
        )

        if output.error:
            return DelegateToAgentOutput(
                agent="novel_writer",
                success=False,
                result=f"章节生成失败：{output.error}",
                structured_data={},
                iterations=output.iterations,
                error=output.error,
            )

        preview = output.chapter_content[:150].replace("\n", " ")
        return DelegateToAgentOutput(
            agent="novel_writer",
            success=True,
            result=(
                f"已生成章节（{output.iterations} 轮推演，"
                f"{output.tool_calls_count} 个工具调用）：{preview}..."
            ),
            structured_data={
                "chapter_content": output.chapter_content,
                "chapter_summary": output.chapter_summary,
                "iterations": output.iterations,
                "tool_calls_count": output.tool_calls_count,
            },
            iterations=output.iterations,
        )

    async def _delegate_world_tree_manager(
        self, input: DelegateToAgentInput
    ) -> DelegateToAgentOutput:
        """委托世界树管理分析干预"""
        from backend.agent.agents.world_tree_manager import get_world_tree_manager

        manager = get_world_tree_manager()
        diff = await manager.analyze_intervention(
            project_id=input.project_id,
            intervention_text=input.task,
        )

        log.info(
            "DelegateToAgentTool._delegate_world_tree_manager DONE: "
            "project_id=%s, risk=%s, consistency=%s, requires_confirm=%s",
            input.project_id,
            diff.risk_level,
            diff.consistency.status,
            diff.requires_double_confirm,
        )

        success = diff.consistency.status != "FAIL"
        result_msg = (
            f"已分析干预影响：{diff.summary}"
            f"（风险={diff.risk_level}，一致性={diff.consistency.status}"
            + ("，需二次确认" if diff.requires_double_confirm else "")
            + "）"
        )

        return DelegateToAgentOutput(
            agent="world_tree_manager",
            success=success,
            result=result_msg,
            structured_data=diff.model_dump(),
            iterations=diff.iterations,
            error=None if success else f"一致性检查失败: {diff.consistency.conflicts}",
        )


# ══════════════════════════════════════════════════════
#  Tool 2：DispatchBackgroundTaskTool（异步委托）
# ══════════════════════════════════════════════════════

class DispatchBackgroundTaskTool(BaseTool):
    """异步派发后台任务给专家 Agent，立即返回 task_id，不等待结果。

    适用场景（管家自主识别的维护任务，用户无需等待）：
    - 章节生成后自动更新 chapter_summary
    - Onboarding 完成后生成封面图
    - 大量历史记忆需要重建索引

    结果通过 EventBus → WS push 推送到前端（task_type 作为事件 key）。
    """

    name = "dispatch_background_task"
    description = (
        "后台异步派发任务给专家 Agent，立即返回，不阻塞当前对话。\n"
        "适用于管家自主识别的维护任务（用户不需要等待结果）。\n"
        "结果通过 WebSocket push 到前端。\n"
        "agent 可选值：novel_writer / world_tree_manager / image_generator\n"
        "task_type 例如：update_chapter_summary / generate_cover / rebuild_memory_index"
    )
    input_schema = DispatchBackgroundTaskInput
    output_schema = DispatchBackgroundTaskOutput

    async def run(
        self,
        input: DispatchBackgroundTaskInput,
        progress_callback=None,
    ) -> DispatchBackgroundTaskOutput:
        task_id = str(uuid.uuid4())

        log.info(
            "DispatchBackgroundTaskTool.run: agent=%s, task_type=%s, "
            "project_id=%s, task_id=%s",
            input.agent, input.task_type, input.project_id, task_id,
        )

        try:
            from backend.core.event_bus import event_bus

            await event_bus.emit(
                f"background_task.{input.agent}",
                task_id=task_id,
                agent=input.agent,
                task=input.task,
                project_id=input.project_id,
                task_type=input.task_type,
            )

            log.info(
                "DispatchBackgroundTaskTool: emitted background_task.%s, task_id=%s",
                input.agent, task_id,
            )

            return DispatchBackgroundTaskOutput(
                task_id=task_id,
                queued=True,
                message=(
                    f"已派发后台任务（{input.task_type}），"
                    f"task_id={task_id[:8]}...，用户无需等待，完成后前端自动更新"
                ),
            )

        except Exception as e:
            log.error(
                "DispatchBackgroundTaskTool.run FAILED: agent=%s, task_type=%s, error=%s",
                input.agent, input.task_type, e, exc_info=True,
            )
            # fire-and-forget 失败不中断管家主流程，返回 queued=False 让 LLM 感知
            return DispatchBackgroundTaskOutput(
                task_id=task_id,
                queued=False,
                message=f"后台任务派发失败（{input.task_type}）：{e}，可忽略继续",
            )


# ══════════════════════════════════════════════════════
#  注册
# ══════════════════════════════════════════════════════

register_tool(DelegateToAgentTool())
register_tool(DispatchBackgroundTaskTool())

