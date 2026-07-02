"""Base Edit 工具（rollback_base）

update_base 已删除（v003 重构后 save_7_artifacts 不存在）。
基座修改请用 edit_artifact(target=...) 增量编辑 9 张表。
"""
from __future__ import annotations

from typing import Optional, Callable, Awaitable
from datetime import datetime
from pathlib import Path

from backend.agent.tools.base import BaseTool, ToolError, register_tool
from backend.agent.tools.schemas import (
    RollbackBaseInput, ProjectDetail,
)
from backend.agent.tools.locks import get_project_lock
from backend.services.project_manager import ProjectManager
from pathlib import Path  # noqa: F401


class RollbackBaseTool(BaseTool):
    name = "rollback_base"
    description = "⚠️ 危险操作：回档到指定章节（confirm=true）"
    input_schema = RollbackBaseInput
    output_schema = ProjectDetail

    def __init__(self):
        self._pm = ProjectManager()

    def is_dangerous(self) -> bool:
        return True

    async def run(
        self, input: RollbackBaseInput, progress_callback=None
    ) -> ProjectDetail:
        lock = get_project_lock(input.project_id)
        if lock.locked():
            return ToolError(
                code="CONCURRENT_ROLLBACK",
                message=f"项目 {input.project_id} 正在执行其他回档",
            )
        async with lock:
            try:
                if progress_callback:
                    await progress_callback({"step": "rolling_back", "percentage": 0})
                result = await self._pm.rollback(
                    project_id=input.project_id,
                    to_chapter=input.to_chapter,
                    confirm=True,
                )
                if progress_callback:
                    await progress_callback({"step": "done", "percentage": 100})
                return ProjectDetail(
                    id=input.project_id,
                    name="",
                    chapters=[],
                )
            except FileNotFoundError as e:
                self._pm.log.warning("rollback_base FileNotFoundError: project=%s, err=%s", input.project_id, e)
                return ToolError(code="NOT_FOUND", message=str(e))
            except ValueError as e:
                self._pm.log.warning("rollback_base ValueError: project=%s, err=%s", input.project_id, e)
                return ToolError(code="ROLLBACK_FAILED", message=str(e))
            except Exception as e:
                self._pm.log.error("rollback_base 异常: project=%s", input.project_id, exc_info=True)
                return ToolError(code="ROLLBACK_FAILED", message=str(e))


register_tool(RollbackBaseTool())
