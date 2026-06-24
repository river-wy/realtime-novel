"""Project 路由（4 个：list/create/load/delete）

对应 api.md §B.1
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Any, Literal

from backend.persistence import ProjectDeletedRepository, ConversationRepository, MessageRole  # noqa: F401
from backend.services.project_manager import ProjectManager

router = APIRouter(prefix="/api/projects", tags=["projects"])
_pm = ProjectManager()


class ProjectInfo(BaseModel):
    id: str
    name: str
    palette: str
    # 探索度
    exploration_level: str = "standard"
    chapter_count: int = 0
    last_updated: Optional[str] = None
    # onboard 续接用
    onboarding_step: Optional[int] = None  # null=从未进过, 0=未开始, 1-4=进行中
    status: Optional[str] = "not_started"  # not_started / in_progress / completed
    # v0.9: 世界封面图
    cover_image_url: Optional[str] = None


class ProjectListResponse(BaseModel):
    total: int
    projects: list[ProjectInfo]


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    palette: str = Field(default="", min_length=0, max_length=500)
    # 创建时可指定探索度，默认 standard
    exploration_level: Literal["conservative", "standard", "wild"] = Field(
        default="standard",
        description="探索度: conservative(严守) / standard(平衡) / wild(大胆)"
    )
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
    # v0.8: 探索度
    exploration_level: str = "standard"
    seven_artifacts: Optional[dict[str, Any]] = None
    world_tree: Optional[dict[str, Any]] = None
    chapters: Optional[list[dict]] = None
    # onboard 续接用
    onboarding_step: Optional[int] = None      # 已完成到哪步 (0=未开始, 1-4=进行中)
    onboarding_payload: Optional[dict[str, Any]] = None  # 已填入的 payload (续接回填用)
    # v0.9: 世界封面图
    cover_image_url: Optional[str] = None


class UpdateExplorationLevelRequest(BaseModel):
    exploration_level: Literal["conservative", "standard", "wild"]


class UpdateExplorationLevelResponse(BaseModel):
    project_id: str
    exploration_level: str
    message: str


class DeleteProjectResponse(BaseModel):
    id: str
    deleted_at: str
    chapters_removed: int
    trash_path: str


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    limit: int = Query(20, ge=1, le=500),
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
    """创建项目（v0.4.1 落库到 messages 表，v0.8 支持 exploration_level）"""
    try:
        # v0.8: 传 exploration_level 给 _pm
        result = await _pm.create(req.name, req.palette, req.initial_prompt, exploration_level=req.exploration_level)
    except FileExistsError as e:
        raise HTTPException(409, f"Project already exists: {req.name}")
    # v0.4.1 落库 (via ConversationRepository)
    conv_repo = ConversationRepository()
    conv = await conv_repo.get_or_create_active_conversation("default")
    await conv_repo.add_message(
        conversation_id=conv.id,
        role=MessageRole.TOOL,
        tool_results={"name": "create_project",
                      "args": {"name": req.name, "palette": req.palette, "initial_prompt": req.initial_prompt,
                               "exploration_level": req.exploration_level},
                      "result": result},
        project_id=result.get("id"),
    )
    return CreateProjectResponse(
        id=result.get("id", ""),
        name=req.name,
        created_at=str(result.get("created_at", "")),
        onboarding_required=True,
    )


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(project_id: str):
    """加载项目详情（v0.8: 含 exploration_level）"""
    project = await _pm.load(project_id)
    if project is None:
        raise HTTPException(404, f"Project not found: {project_id}")
    return ProjectDetailResponse(
        id=project.get("id", project_id),
        name=project.get("name", ""),
        palette=project.get("palette", ""),
        exploration_level=project.get("exploration_level", "standard"),
        seven_artifacts=project.get("seven_artifacts"),
        world_tree=project.get("world_tree"),
        chapters=project.get("chapters"),
        onboarding_step=project.get("onboarding_step"),
        onboarding_payload=project.get("onboarding_payload") or None,
        cover_image_url=project.get("cover_image_url"),  # v0.9
    )


@router.patch("/{project_id}/exploration-level", response_model=UpdateExplorationLevelResponse)
async def update_exploration_level(
    project_id: str,
    req: UpdateExplorationLevelRequest,
):
    """v0.8: 切换项目探索度 (conservative/standard/wild)

    探索度影响后续章节生成 + 世界树管理的 LLM 参数 (Temperature/max_tokens)
    - conservative: 严守用户输入
    - standard:     平衡
    - wild:         大胆发散
    """
    try:
        await _pm.update_exploration_level(project_id, req.exploration_level)
    except FileNotFoundError:
        raise HTTPException(404, f"Project not found: {project_id}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return UpdateExplorationLevelResponse(
        project_id=project_id,
        exploration_level=req.exploration_level,
        message=f"探索度已切换为 {req.exploration_level}, 后续章节生成将使用新参数",
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
    # v0.4.1 落库 (via ConversationRepository)
    conv_repo = ConversationRepository()
    conv = await conv_repo.get_or_create_active_conversation("default")
    await conv_repo.add_message(
        conversation_id=conv.id,
        role=MessageRole.TOOL,
        tool_results={"name": "delete_project",
                      "args": {"project_id": project_id, "confirm": confirm},
                      "result": result},
        project_id=project_id,
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
