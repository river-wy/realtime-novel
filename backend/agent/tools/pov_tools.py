"""pov_tools.py：switch_pov 工具

current_pov 存 char_id，写入前校验角色存在，返回包含 name。
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from backend.agent.tools.base import BaseTool, ToolError, register_tool
from backend.agent.tools.schemas import (
    SwitchPovInput, SwitchPovResult,
)
from backend.persistence import ProjectRepository


class SwitchPovTool(BaseTool):
    """切换 POV 角色（下一章节开始用新 POV）。传入 new_pov_char_id（格式: char-xxxxxxxx）"""
    name = "switch_pov"
    description = "切换 POV 角色（下一章节开始用新 POV）。传入 new_pov_char_id（格式: char-xxxxxxxx）"
    input_schema = SwitchPovInput
    output_schema = SwitchPovResult

    def __init__(self):
        self._project_repo = ProjectRepository()

    async def run(
        self, input: SwitchPovInput, progress_callback=None
    ) -> SwitchPovResult:
        try:
            # 1. 校验项目存在
            project = self._project_repo.get(input.project_id)
            if project is None:
                return ToolError(
                    code="NOT_FOUND",
                    message=f"Project not found: {input.project_id}",
                )

            # 2. 校验目标角色存在，取 name
            char = self._project_repo.get_character(input.project_id, input.new_pov_char_id)
            if char is None:
                return ToolError(
                    code="CHAR_NOT_FOUND",
                    message=f"Character not found: {input.new_pov_char_id}（请先用 edit_artifact 创建角色）",
                )
            new_pov_name = char.get("name", "") if isinstance(char, dict) else getattr(char, "name", "")

            # 3. 记录前 POV char_id（v003：从 project_state 表读，Project model 不再含 current_pov）
            state = self._project_repo.get_project_state(input.project_id)
            previous_pov_char_id = state.current_pov if state else ""

            # 4. 写新 POV（v003：迁入 project_state 表）
            self._project_repo.upsert_project_state(
                input.project_id, current_pov=input.new_pov_char_id
            )

            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return SwitchPovResult(
                project_id=input.project_id,
                previous_pov_char_id=previous_pov_char_id,
                new_pov_char_id=input.new_pov_char_id,
                new_pov_name=new_pov_name,
            )
        except Exception as e:
            log.error("switch_pov 失败: project_id=%s, new_pov=%s, error=%s", input.project_id, input.new_pov_char_id, e, exc_info=True)
            return ToolError(code="SWITCH_POV_FAILED", message=str(e))


register_tool(SwitchPovTool())
