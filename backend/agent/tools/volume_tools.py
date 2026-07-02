"""volume_tools 工具

文笔家 ReAct loop 调 generate_volume_summary 工具生成卷的 1000 字总结。

设计：
- 背后走 WTM.generate_volume_summary
- auto_complete_volume=False（默认）：只生成 summary，保留 status=in_progress
- auto_complete_volume=True：生成 summary 后调 WTM.complete_volume
- 调用记录写入 WTM 默认 session（不污染文笔家 session）
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from backend.agent.tools.base import BaseTool, ToolError, register_tool
from backend.agent.tools.schemas import GenerateVolumeSummaryInput, GenerateVolumeSummaryOutput

log = logging.getLogger(__name__)


class GenerateVolumeSummaryTool(BaseTool):
    """生成卷的 1000 字总结

    背后走 WTM.generate_volume_summary — 包含 prompt + LLM 调用 + 落库
    """
    name = "generate_volume_summary"
    description = (
        "为本卷（volume_id 指定）生成 ~1000 字的整卷总结。"
        "总结会写入 volumes 表的 summary 字段，供后续卷 context 复用（节省 token）。"
        "【重要】仅在本卷所有章节都生成完后调。"
        "auto_complete_volume=True 会同时把卷状态改成 completed（完结）；"
        "auto_complete_volume=False（默认）只生成 summary，卷仍处于 in_progress。"
    )
    input_schema = GenerateVolumeSummaryInput
    output_schema = GenerateVolumeSummaryOutput

    async def run(
        self,
        input: GenerateVolumeSummaryInput,
        progress_callback=None,
    ) -> GenerateVolumeSummaryOutput:
        try:
            from backend.agent.agents.world_tree_manager import get_world_tree_manager

            wtm = get_world_tree_manager()

            log.info(
                "generate_volume_summary: START project_id=%s, volume_id=%s, "
                "auto_complete_volume=%s",
                input.project_id, input.volume_id, input.auto_complete_volume,
            )

            # 1. 调 WTM.generate_volume_summary
            summary_text = await wtm.generate_volume_summary(
                project_id=input.project_id,
                volume_id=input.volume_id,
            )

            # 2. 可选：完结卷
            auto_completed = False
            final_status = "in_progress"
            if input.auto_complete_volume:
                result: Dict[str, Any] = await wtm.complete_volume(
                    project_id=input.project_id,
                    volume_id=input.volume_id,
                    auto_generate_summary=False,  # 已生成，不重复
                )
                auto_completed = True
                final_status = result.get("status", "completed")
                # 如果 WTM 返回了更新后的 summary，用它
                if result.get("summary"):
                    summary_text = result["summary"]

            log.info(
                "generate_volume_summary: DONE project_id=%s, volume_id=%s, "
                "summary_len=%d, auto_completed=%s, status=%s",
                input.project_id, input.volume_id,
                len(summary_text), auto_completed, final_status,
            )

            return GenerateVolumeSummaryOutput(
                volume_id=input.volume_id,
                summary=summary_text,
                summary_len=len(summary_text),
                auto_completed=auto_completed,
                status=final_status,
            )
        except ValueError as ve:
            # volume 不存在
            log.error(
                "generate_volume_summary: 业务错误 project_id=%s, volume_id=%s, error=%s",
                input.project_id, input.volume_id, ve,
            )
            return ToolError(
                code="VOLUME_NOT_FOUND",
                message=str(ve),
            )
        except Exception as e:
            log.error(
                "generate_volume_summary: 异常 project_id=%s, volume_id=%s, error=%s",
                input.project_id, input.volume_id, e,
                exc_info=True,
            )
            return ToolError(
                code="VOLUME_SUMMARY_FAILED",
                message=f"卷总结生成失败: {e}",
                details={"project_id": input.project_id, "volume_id": input.volume_id},
            )


register_tool(GenerateVolumeSummaryTool())
