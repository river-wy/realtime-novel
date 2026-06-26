"""Action 路由（4 个：interventions / rollback / image / base PATCH）

对应 api.md §B.3

Onboarding 相关路由已迁移到 onboarding_routes.py
"""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Literal

from backend.persistence import ChapterStatusRepository, ConversationRepository, MessageRole
from backend.services.intervention_parser import InterventionParser
from backend.services.project_manager import ProjectManager

router = APIRouter(prefix="/api/projects", tags=["actions"])
_intervention = InterventionParser()
_pm = ProjectManager()
_cs_repo = ChapterStatusRepository()


# ============ /interventions ============

class InterventionRequest(BaseModel):
    intervention: Optional[str] = None
    actor_feedback: Optional[str] = None
    actor_character: Optional[str] = None


class InterventionResponse(BaseModel):
    project_id: str
    accepted: bool = True
    next_chapter_will_apply: bool = True


@router.post("/{project_id}/interventions", response_model=InterventionResponse)
async def submit_intervention(project_id: str, req: InterventionRequest):
    """提交剧情干预（v0.4.1 落库）"""
    try:
        result = await _intervention.add(
            project_id,
            req.intervention,
            req.actor_feedback,
            req.actor_character,
        )
    except Exception as e:
        raise HTTPException(500, str(e))
    # 落库
    conv_repo = ConversationRepository()
    conv = await conv_repo.get_or_create_active_conversation("default")
    await conv_repo.add_message(
        conversation_id=conv.id,
        role=MessageRole.TOOL,
        tool_results={
            "name": "intervene",
            "args": {
                "intervention": req.intervention,
                "actor_feedback": req.actor_feedback,
                "actor_character": req.actor_character,
            },
            "result": result if isinstance(result, dict) else {"raw": str(result)},
        },
        project_id=project_id,
    )
    return InterventionResponse(
        project_id=project_id,
        accepted=True,
        next_chapter_will_apply=True,
    )


# ============ /rollback ============

class RollbackResponse(BaseModel):
    project_id: str
    kept_chapters: int
    removed_chapters: int
    new_node_tree_state: Optional[dict] = None
    rolled_back_at: str


@router.post("/{project_id}/rollback", response_model=RollbackResponse)
async def rollback_project(
    project_id: str,
    to_chapter: int = Query(..., ge=1),
    confirm: bool = Query(..., description="Must be true"),
):
    """⚠️ 危险操作：回档 — 薄路由，调 rollback_base tool（v0.4.1 落库）"""
    if not confirm:
        raise HTTPException(400, "confirm query param must be true")
    try:
        output = await _pm.rollback(project_id, to_chapter=to_chapter, confirm=True)
    except Exception as e:
        raise HTTPException(500, str(e))
    # 落库
    conv_repo = ConversationRepository()
    conv = await conv_repo.get_or_create_active_conversation("default")
    await conv_repo.add_message(
        conversation_id=conv.id,
        role=MessageRole.TOOL,
        tool_results={
            "name": "rollback_to_node",
            "args": {"project_id": project_id, "to_chapter": to_chapter, "confirm": confirm},
            "result": output,
        },
        project_id=project_id,
    )
    return RollbackResponse(
        project_id=project_id,
        kept_chapters=output.get("kept_chapters", 0),
        removed_chapters=output.get("removed_chapters", 0),
        new_node_tree_state=None,
        rolled_back_at=datetime.now().isoformat(),
    )


# ============ /image ============

class ImageRequest(BaseModel):
    style_hint: Optional[str] = None


class ImageResponse(BaseModel):
    project_id: str
    image_url: str
    generated_at: str
    cache_hit: bool = False


@router.post("/{project_id}/image", response_model=ImageResponse)
async def generate_image(project_id: str, req: ImageRequest):
    """生成主立绘 — 薄路由，调 generate_image tool（v0.4.1 落库）"""
    from backend.agent.tools import get_tool
    from backend.agent.tools.schemas import GenerateImageInput
    from backend.agent.tools.base import ToolError
    tool = get_tool("generate_image")
    input_obj = GenerateImageInput(project_id=project_id, style_hint=req.style_hint)
    output = await tool.run(input_obj)
    if isinstance(output, ToolError):
        raise HTTPException(500, f"Image generation failed: {output.message}")
    # 落库
    result_dict = output.model_dump() if hasattr(output, "model_dump") else {"_raw": str(output)}
    conv_repo = ConversationRepository()
    conv = await conv_repo.get_or_create_active_conversation("default")
    await conv_repo.add_message(
        conversation_id=conv.id,
        role=MessageRole.TOOL,
        tool_results={
            "name": "generate_image",
            "args": {"project_id": project_id, "style_hint": req.style_hint},
            "result": result_dict,
        },
        project_id=project_id,
    )
    return ImageResponse(
        project_id=output.project_id,
        image_url=output.image_url,
        generated_at=output.generated_at,
        cache_hit=output.cache_hit,
    )


# ============ PATCH /base ============

class UpdateBaseRequest(BaseModel):
    key: Literal["name", "palette", "world_tree", "main_plot", "style_pack", "seed_table", "genre_resonance"]
    new_value: str = Field(..., min_length=1)


class UpdateBaseResponse(BaseModel):
    project_id: str
    key: str
    old_value_preview: str
    new_value_preview: str
    updated_at: str
    chapters_affected: list[int] = Field(default_factory=list)


@router.patch("/{project_id}/base", response_model=UpdateBaseResponse)
async def update_base(project_id: str, req: UpdateBaseRequest):
    """改 7 件基座 — 薄路由，调 update_base tool（v0.4.1 落库）"""
    from backend.agent.tools import get_tool
    from backend.agent.tools.schemas import UpdateBaseInput
    from backend.agent.tools.base import ToolError
    tool = get_tool("update_base")
    input_obj = UpdateBaseInput(
        project_id=project_id, key=req.key, new_value=req.new_value
    )
    output = await tool.run(input_obj)
    if isinstance(output, ToolError):
        raise HTTPException(500, f"Update base failed: {output.message}")
    # 落库
    result_dict = output.model_dump() if hasattr(output, "model_dump") else {"_raw": str(output)}
    conv_repo = ConversationRepository()
    conv = await conv_repo.get_or_create_active_conversation("default")
    await conv_repo.add_message(
        conversation_id=conv.id,
        role=MessageRole.TOOL,
        tool_results={
            "name": "update_base",
            "args": {"project_id": project_id, "key": req.key, "new_value_preview": req.new_value[:100]},
            "result": result_dict,
        },
        project_id=project_id,
    )
    return UpdateBaseResponse(
        project_id=output.project_id,
        key=output.key,
        old_value_preview=output.old_value_preview,
        new_value_preview=output.new_value_preview,
        updated_at=datetime.now().isoformat(),
        chapters_affected=output.chapters_affected,
    )
