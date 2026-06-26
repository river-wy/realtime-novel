"""style_tools.py — adjust_style 工具

v0.6.2 重构：从 style_charter 切换为 style_pack（操作 projects.style_pack_id）
v0.6 重构：从 v0_4_new_tools.py 拆出
v0.4 原版 broken：写 7_artifacts.yaml 文件（v0.4.1 删了，7 件全入 DB）
v0.6 修复：复用 update_base 工具（不再写文件）
"""
from __future__ import annotations

from typing import Optional

from backend.agent.tools.base import BaseTool, ToolError, register_tool
from backend.agent.tools.schemas import (
    AdjustStyleInput, AdjustStyleResult,
)


class AdjustStyleTool(BaseTool):
    """切换写作笔风（更新项目的 style_pack_id）"""
    name = "adjust_style"
    description = "切换写作笔风（更新项目的 style_pack_id）"
    input_schema = AdjustStyleInput
    output_schema = AdjustStyleResult

    async def run(
        self, input: AdjustStyleInput, progress_callback=None
    ) -> AdjustStyleResult:
        try:
            from backend.persistence import ProjectRepository

            repo = ProjectRepository()
            repo.update_style_pack_id(input.project_id, input.style_pack_id)

            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return AdjustStyleResult(
                project_id=input.project_id,
                style_pack_updated=True,
            )
        except Exception as e:
            return ToolError(code="ADJUST_STYLE_FAILED", message=str(e))


register_tool(AdjustStyleTool())
