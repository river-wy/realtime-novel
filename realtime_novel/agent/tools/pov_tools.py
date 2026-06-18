"""pov_tools.py — switch_pov 工具

v0.6 重构：从 v0_4_new_tools.py 拆出
v0.4 原版 broken：写 7_artifacts.yaml 文件
v0.6 修复：改用 ProjectRepository.update_current_pov 写 DB
"""
from __future__ import annotations

from realtime_novel.agent.tools.base import BaseTool, ToolError, register_tool
from realtime_novel.agent.tools.schemas import (
    SwitchPovInput, SwitchPovResult,
)
from realtime_novel.persistence import ProjectRepository


class SwitchPovTool(BaseTool):
    """切换 POV 角色（下一章节开始用新 POV）

    v0.6 实现：调 ProjectRepository.update_current_pov
    """
    name = "switch_pov"
    description = "切换 POV 角色（下一章节开始用新 POV）"
    input_schema = SwitchPovInput
    output_schema = SwitchPovResult

    def __init__(self):
        self._project_repo = ProjectRepository()

    async def run(
        self, input: SwitchPovInput, progress_callback=None
    ) -> SwitchPovResult:
        try:
            # 读 previous_pov
            project = self._project_repo.get(input.project_id)
            if project is None:
                return ToolError(
                    code="NOT_FOUND",
                    message=f"Project not found: {input.project_id}",
                )
            previous_pov = project.current_pov or ""

            # 写新 POV 到 DB
            self._project_repo.update_current_pov(input.project_id, input.new_pov_character)

            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return SwitchPovResult(
                project_id=input.project_id,
                previous_pov=previous_pov,
                new_pov=input.new_pov_character,
            )
        except Exception as e:
            return ToolError(code="SWITCH_POV_FAILED", message=str(e))


register_tool(SwitchPovTool())
