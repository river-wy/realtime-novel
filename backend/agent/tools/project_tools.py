"""Project 工具（load_project / create_project / delete_project）

对应 core.md §B.1
"""
from __future__ import annotations

from typing import Optional, Callable, Awaitable, List
from pydantic import BaseModel, Field

from backend.agent.tools.base import BaseTool, ToolError, register_tool
from backend.agent.tools.schemas import (
    LoadProjectInput, CreateProjectInput, DeleteProjectInput, ProjectDetail,
)
from backend.services.project_manager import ProjectManager




# ============ 列项目工具 ============

class ListProjectsInput(BaseModel):
    """列出用户项目（管家"我有什么项目"用）"""
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    include_deleted: bool = Field(
        default=False,
        description="是否含已软删项目（默认 false）",
    )


class ProjectListItem(BaseModel):
    """项目列表项（精简版，避免 LLM 上下文爆炸）"""
    id: str
    name: str
    chapter_count: int = 0
    status: str = "not_started"  # not_started / in_progress / completed
    exploration_level: str = "standard"
    onboarding_step: Optional[int] = None
    last_updated: Optional[str] = None
    cover_image_url: Optional[str] = None


class ListProjectsOutput(BaseModel):
    """列项目输出"""
    projects: List[ProjectListItem] = Field(default_factory=list)
    total: int = Field(default=0, description="当前返回数量")
    has_more: bool = Field(default=False)


class LoadProjectTool(BaseTool):
    name = "load_project"
    description = "加载项目详情（7 件基座 + 世界树 + 章节列表）"
    input_schema = LoadProjectInput
    output_schema = ProjectDetail

    def __init__(self):
        self._manager = ProjectManager()

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
        self._manager = ProjectManager()

    async def run(self, input: CreateProjectInput, progress_callback=None) -> ProjectDetail:
        try:
            project = await self._manager.create(
                name=input.name,
                palette=input.palette,
                initial_prompt=input.initial_prompt,
                exploration_level=input.exploration_level,
            )
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
        self._manager = ProjectManager()

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




class ListProjectsTool(BaseTool):
    """列出项目

    管家"我有什么项目"用。返回精简版（不含 7 件基座，避免 LLM 上下文爆炸）。
    软删项目默认隐藏（include_deleted=true 显式打开）。
    """
    name = "list_projects"
    description = (
        "列出用户项目（精简版：id/name/chapter_count/status/last_updated）。"
        "默认跳过已软删项目。可分页。"
    )
    input_schema = ListProjectsInput
    output_schema = ListProjectsOutput

    def __init__(self):
        self._manager = ProjectManager()

    async def run(self, input: ListProjectsInput, progress_callback=None) -> ListProjectsOutput:
        try:
            from backend.persistence import ProjectRepository
            repo = ProjectRepository()
            # 一次拉 limit+offset（跟 PM.list_projects 同款）
            rows = repo.list_all(limit=input.limit + input.offset)
            # 软删过滤
            if not input.include_deleted:
                rows = [r for r in rows if not getattr(r, "deleted_at", None)]
            page = rows[input.offset:input.offset + input.limit]
            # 组装精简版
            items = []
            for r in page:
                # 计算 status 跟 chapter_count
                try:
                    from backend.persistence import ChapterRepository
                    chap_count = ChapterRepository().count_chapters(r.id)
                except Exception:
                    chap_count = 0
                status = (
                    "completed" if chap_count > 0
                    else "in_progress" if getattr(r, "current_step", None)
                    else "not_started"
                )
                items.append(ProjectListItem(
                    id=r.id,
                    name=r.name or "",
                    chapter_count=chap_count,
                    status=status,
                    exploration_level=r.exploration_level or "standard",
                    last_updated=r.updated_at.isoformat() if r.updated_at else None,
                    cover_image_url=r.cover_image_url,
                ))
            return ListProjectsOutput(
                projects=items,
                total=len(items),
                has_more=len(rows) > input.offset + input.limit,
            )
        except Exception as e:
            # 失败不抛错，返空列表（避免 LLM 决策阻断）
            return ListProjectsOutput(projects=[], total=0, has_more=False)


register_tool(ListProjectsTool())
