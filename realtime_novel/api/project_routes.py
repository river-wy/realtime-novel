"""Project 路由（4 个：list/create/load/delete）

对应 api.md §B.1
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Any

from realtime_novel.services.async_wrappers import AsyncProjectManager
from realtime_novel.persistence import ProjectDeletedRepository  # noqa: F401
from realtime_novel.api.messages import record_tool_call, get_or_create_conversation

router = APIRouter(prefix="/api/projects", tags=["projects"])
_pm = AsyncProjectManager()


class ProjectInfo(BaseModel):
    id: str
    name: str
    palette: str
    chapter_count: int = 0
    last_updated: Optional[str] = None


class ProjectListResponse(BaseModel):
    total: int
    projects: list[ProjectInfo]


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    palette: str = Field(..., min_length=1)
    initial_prompt: Optional[str] = None


class CreateProjectResponse(BaseModel):
    id: str
    name: str
    created_at: str
    onboarding_required: bool = True


class ProjectDetailResponse(BaseModel):
    id: str
    name: str
    palette: str
    seven_artifacts: Optional[dict[str, Any]] = None
    world_tree: Optional[dict[str, Any]] = None
    chapters: Optional[list[dict]] = None


class DeleteProjectResponse(BaseModel):
    id: str
    deleted_at: str
    chapters_removed: int
    trash_path: str


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_deleted: bool = Query(False),
):
    """列出项目（默认过滤已删除）"""
    projects = await _pm.list_projects(limit=limit, offset=offset)
    return ProjectListResponse(
        total=len(projects),
        projects=[ProjectInfo(**p) for p in projects],
    )


@router.post("", response_model=CreateProjectResponse, status_code=201)
async def create_project(req: CreateProjectRequest):
    """创建项目（v0.4.1 落库到 messages 表）"""
    try:
        result = await _pm.create(req.name, req.palette, req.initial_prompt)
    except FileExistsError as e:
        raise HTTPException(409, f"Project already exists: {req.name}")
    # v0.4.1 落库（业务接口调用走 record_tool_call）
    conv_id = get_or_create_conversation(user_id="default", project_id=result.get("id"))
    record_tool_call(
        conversation_id=conv_id,
        tool_name="create_project",
        args={"name": req.name, "palette": req.palette, "initial_prompt": req.initial_prompt},
        result=result,
    )
    return CreateProjectResponse(
        id=result.get("id", ""),
        name=req.name,
        created_at=str(result.get("created_at", "")),
        onboarding_required=True,
    )


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(project_id: str):
    """加载项目详情"""
    project = await _pm.load(project_id)
    if project is None:
        raise HTTPException(404, f"Project not found: {project_id}")
    return ProjectDetailResponse(
        id=project.get("id", project_id),
        name=project.get("name", ""),
        palette=project.get("palette", ""),
        seven_artifacts=project.get("seven_artifacts"),
        world_tree=project.get("world_tree"),
        chapters=project.get("chapters"),
    )


@router.delete("/{project_id}", response_model=DeleteProjectResponse)
async def delete_project(
    project_id: str,
    confirm: bool = Query(..., description="Must be true"),
):
    """⚠️ 危险操作：删除项目（v1.3 软删方案 b）— 薄路由，调 manager.soft_delete"""
    if not confirm:
        raise HTTPException(400, "confirm query param must be true")
    try:
        result = await _pm.soft_delete(project_id, confirm=True)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    # v0.4.1 落库
    conv_id = get_or_create_conversation(user_id="default", project_id=project_id)
    record_tool_call(
        conversation_id=conv_id,
        tool_name="delete_project",
        args={"project_id": project_id, "confirm": confirm},
        result=result,
    )
    # 统计 chapter 数
    from pathlib import Path
    chapters_removed = 0
    if Path(result["trash_path"]).exists():
        chapters_dir = Path(result["trash_path"]) / "chapters"
        if chapters_dir.exists():
            chapters_removed = len(list(chapters_dir.glob("chapter_*.md")))
    return DeleteProjectResponse(
        id=project_id,
        deleted_at=result["deleted_at"],
        chapters_removed=chapters_removed,
        trash_path=result["trash_path"],
    )
