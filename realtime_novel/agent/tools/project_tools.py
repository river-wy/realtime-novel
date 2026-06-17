"""Project 工具（load_project / create_project / delete_project）

对应 core.md §B.1
"""
from __future__ import annotations

from typing import Optional, Callable, Awaitable
from pydantic import BaseModel

from realtime_novel.agent.tools.base import BaseTool, ToolError, register_tool
from realtime_novel.agent.tools.schemas import (
    LoadProjectInput, CreateProjectInput, DeleteProjectInput, ProjectDetail,
)
from realtime_novel.services.async_wrappers import AsyncProjectManager


class LoadProjectTool(BaseTool):
    name = "load_project"
    description = "加载项目详情（7 件基座 + 世界树 + 章节列表）"
    input_schema = LoadProjectInput
    output_schema = ProjectDetail

    def __init__(self):
        self._manager = AsyncProjectManager()

    async def run(self, input: LoadProjectInput, progress_callback=None) -> ProjectDetail:
        try:
            if progress_callback:
                await progress_callback({"step": "loading", "percentage": 0})
            project = await self._manager.load(input.project_id)
            if project is None:
                return ToolError(code="NOT_FOUND", message=f"Project not found: {input.project_id}")
            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return ProjectDetail(
                id=project.get("id", input.project_id),
                name=project.get("name", ""),
                palette=project.get("palette", ""),
                seven_artifacts=project.get("seven_artifacts"),
                world_tree=project.get("world_tree"),
                chapters=project.get("chapters"),
            )
        except Exception as e:
            return ToolError(code="LOAD_FAILED", message=str(e))


class CreateProjectTool(BaseTool):
    name = "create_project"
    description = "创建新项目（初始化文件 + DB）"
    input_schema = CreateProjectInput
    output_schema = ProjectDetail

    def __init__(self):
        self._manager = AsyncProjectManager()

    async def run(self, input: CreateProjectInput, progress_callback=None) -> ProjectDetail:
        try:
            project = await self._manager.create(input.name, input.palette, input.initial_prompt)
            return ProjectDetail(
                id=project.get("id", ""),
                name=input.name,
                palette=input.palette,
                seven_artifacts=None, world_tree=None, chapters=[],
            )
        except FileExistsError as e:
            return ToolError(code="ALREADY_EXISTS", message=str(e))
        except Exception as e:
            return ToolError(code="CREATE_FAILED", message=str(e))


class DeleteProjectTool(BaseTool):
    name = "delete_project"
    description = "⚠️ 危险操作：删除项目（移到 .trash/ 软删除）"
    input_schema = DeleteProjectInput
    output_schema = ProjectDetail

    def __init__(self):
        self._manager = AsyncProjectManager()

    def is_dangerous(self) -> bool:
        return True

    async def run(self, input: DeleteProjectInput, progress_callback=None) -> ProjectDetail:
        # input.confirm 已被 Literal[True] 强制，类型层保证是 True
        try:
            result = await self._manager.delete(input.project_id, confirm=True)
            return ProjectDetail(
                id=input.project_id,
                name=result.get("project_id", input.project_id),
                palette="",
            )
        except FileNotFoundError as e:
            return ToolError(code="NOT_FOUND", message=str(e))
        except Exception as e:
            return ToolError(code="DELETE_FAILED", message=str(e))


# 注册
register_tool(LoadProjectTool())
register_tool(CreateProjectTool())
register_tool(DeleteProjectTool())
