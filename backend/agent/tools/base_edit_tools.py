"""Base Edit 工具（update_base / rollback_base）

对应 core.md §B.1
"""
from __future__ import annotations

from typing import Optional, Callable, Awaitable
from datetime import datetime
from pathlib import Path

from backend.agent.tools.base import BaseTool, ToolError, register_tool
from backend.agent.tools.schemas import (
    UpdateBaseInput, UpdateBaseResult, RollbackBaseInput, ProjectDetail,
)
from backend.agent.tools.locks import get_project_lock
from backend.services.project_manager import ProjectManager
from pathlib import Path  # noqa: F401  (保留 import 以防 Path 被未来代码需要)


class UpdateBaseTool(BaseTool):
    name = "update_base"
    description = "改 7 件基座之一（key ∈ 7 件名）"
    input_schema = UpdateBaseInput
    output_schema = UpdateBaseResult

    def __init__(self):
        self._manager = ProjectManager()

    async def run(
        self, input: UpdateBaseInput, progress_callback=None
    ) -> UpdateBaseResult:
        try:
            if progress_callback:
                await progress_callback({"step": "loading", "percentage": 0})
            # 走 manager（v0.4 重构 P0-1）
            result = await self._manager.update_base(
                project_id=input.project_id,
                key=input.key,
                new_value=input.new_value,
            )
            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return UpdateBaseResult(**result)
        except FileNotFoundError as e:
            return ToolError(code="NOT_FOUND", message=str(e))
        except Exception as e:
            return ToolError(code="UPDATE_FAILED", message=str(e))


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
                # 走 manager（v0.4 重构 P0-1）
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
                    palette="",
                    chapters=[],
                )
            except FileNotFoundError as e:
                return ToolError(code="NOT_FOUND", message=str(e))
            except ValueError as e:
                return ToolError(code="ROLLBACK_FAILED", message=str(e))
            except Exception as e:
                return ToolError(code="ROLLBACK_FAILED", message=str(e))


register_tool(UpdateBaseTool())
register_tool(RollbackBaseTool())
