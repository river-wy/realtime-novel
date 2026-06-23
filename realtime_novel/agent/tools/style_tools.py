"""style_tools.py — adjust_style 工具

v0.6 重构：从 v0_4_new_tools.py 拆出
v0.4 原版 broken：写 7_artifacts.yaml 文件（v0.4.1 删了，7 件全入 DB）
v0.6 修复：复用 update_base 工具（不再写文件）
"""
from __future__ import annotations

from typing import Optional

from realtime_novel.agent.tools.base import BaseTool, ToolError, register_tool
from realtime_novel.agent.tools.schemas import (
    AdjustStyleInput, AdjustStyleResult,
)


class AdjustStyleTool(BaseTool):
    """调整文风（追加 directive 到 style_charter.notes）

    v0.6 实现：调 update_base key="style_charter" 完整重写 style_charter JSON
    """
    name = "adjust_style"
    description = "调整文风（追加 directive 到 style_charter.notes）"
    input_schema = AdjustStyleInput
    output_schema = AdjustStyleResult

    async def run(
        self, input: AdjustStyleInput, progress_callback=None
    ) -> AdjustStyleResult:
        try:
            # v0.6 改用 update_base 工具（写 DB）
            from realtime_novel.agent.tools.schemas import UpdateBaseInput
            from realtime_novel.persistence import ProjectRepository
            import json

            repo = ProjectRepository()
            all_data = repo.load_all_artifacts(input.project_id)
            style_charter = all_data.get("style_charter", {})
            if not isinstance(style_charter, dict):
                style_charter = {"raw": str(style_charter)}

            # 追加 directive 到 notes
            notes = style_charter.get("notes", [])
            if not isinstance(notes, list):
                notes = [str(notes)]
            notes.append(input.style_directive)
            style_charter["notes"] = notes

            # 写回 DB
            repo.save_7_artifacts(
                project_id=input.project_id,
                world_tree=all_data.get("world_tree", {}),
                style_charter=style_charter,
                genre_resonance=all_data.get("genre_resonance", {}),
                main_plot=all_data.get("main_plot", {}),
                sub_plot=all_data.get("sub_plot", {}),
                character_card=all_data.get("character_card", {}),
                seed_table=all_data.get("seed_table", {}),
            )

            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return AdjustStyleResult(
                project_id=input.project_id,
                style_charter_updated=True,
            )
        except Exception as e:
            return ToolError(code="ADJUST_STYLE_FAILED", message=str(e))


register_tool(AdjustStyleTool())
