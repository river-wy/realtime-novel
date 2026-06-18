"""Action 路由（5 个：onboarding/interventions/rollback/image/base PATCH）

对应 api.md §B.3
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

from realtime_novel.services.async_wrappers import (
    AsyncOnboardingFlow, AsyncInterventionParser, AsyncProjectManager, AsyncRollbackManager,
)
from realtime_novel.persistence import ChapterStatusRepository, get_store
from realtime_novel.api.messages import record_tool_call, get_or_create_conversation

router = APIRouter(prefix="/api/projects", tags=["actions"])
_onboarding = AsyncOnboardingFlow()
_intervention = AsyncInterventionParser()
_pm = AsyncProjectManager()
_rollback = AsyncRollbackManager()
_cs_repo = ChapterStatusRepository()


# ============ /onboarding ============

class OnboardingRequest(BaseModel):
    step: Literal["1a", "1b", "2", "3", "4", "5"]
    payload: dict = Field(default_factory=dict)


class OnboardingResponse(BaseModel):
    step: str
    result: dict
    next_step: Optional[str] = None


@router.post("/{project_id}/onboarding", response_model=OnboardingResponse)
async def onboarding(project_id: str, req: OnboardingRequest):
    """5 步启动链路（v0.4.1 落库）"""
    try:
        result = await _onboarding.step(project_id, req.step, req.payload)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    # v0.4.1 落库
    conv_id = get_or_create_conversation(user_id="default", project_id=project_id)
    record_tool_call(
        conversation_id=conv_id,
        tool_name="onboarding_step",
        args={"step": req.step, "payload": req.payload},
        result=result if isinstance(result, dict) else {"raw": str(result)},
    )
    return OnboardingResponse(
        step=req.step,
        result=result if isinstance(result, dict) else {"raw": str(result)},
        next_step=result.get("next_step") if isinstance(result, dict) else None,
    )


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
    # v0.4.1 落库
    conv_id = get_or_create_conversation(user_id="default", project_id=project_id)
    record_tool_call(
        conversation_id=conv_id,
        tool_name="intervene",
        args={
            "intervention": req.intervention,
            "actor_feedback": req.actor_feedback,
            "actor_character": req.actor_character,
        },
        result=result if isinstance(result, dict) else {"raw": str(result)},
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
    from realtime_novel.agent.tools import get_tool
    from realtime_novel.agent.tools.schemas import RollbackBaseInput
    from realtime_novel.agent.tools.base import ToolError
    tool = get_tool("rollback_base")
    output = await tool.run(RollbackBaseInput(
        project_id=project_id, to_chapter=to_chapter, confirm=True,
    ))
    if isinstance(output, ToolError):
        if output.code == "CONCURRENT_ROLLBACK":
            raise HTTPException(409, output.message)
        raise HTTPException(500, output.message)
    # v0.4.1 落库
    conv_id = get_or_create_conversation(user_id="default", project_id=project_id)
    result_dict = output.model_dump() if hasattr(output, "model_dump") else {"_raw": str(output)}
    record_tool_call(
        conversation_id=conv_id,
        tool_name="rollback_to_node",
        args={"project_id": project_id, "to_chapter": to_chapter, "confirm": confirm},
        result=result_dict,
    )
    return RollbackResponse(
        project_id=project_id,
        kept_chapters=0,
        removed_chapters=0,
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
    from realtime_novel.agent.tools import get_tool
    from realtime_novel.agent.tools.schemas import GenerateImageInput
    from realtime_novel.agent.tools.base import ToolError
    tool = get_tool("generate_image")
    input_obj = GenerateImageInput(project_id=project_id, style_hint=req.style_hint)
    output = await tool.run(input_obj)
    if isinstance(output, ToolError):
        raise HTTPException(500, f"Image generation failed: {output.message}")
    # v0.4.1 落库
    conv_id = get_or_create_conversation(user_id="default", project_id=project_id)
    result_dict = output.model_dump() if hasattr(output, "model_dump") else {"_raw": str(output)}
    record_tool_call(
        conversation_id=conv_id,
        tool_name="generate_image",
        args={"project_id": project_id, "style_hint": req.style_hint},
        result=result_dict,
    )
    return ImageResponse(
        project_id=output.project_id,
        image_url=output.image_url,
        generated_at=output.generated_at,
        cache_hit=output.cache_hit,
    )


# ============ PATCH /base ============

class UpdateBaseRequest(BaseModel):
    key: Literal["name", "palette", "world_tree", "main_plot", "style_charter", "seed_table", "genre_resonance"]
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
    from realtime_novel.agent.tools import get_tool
    from realtime_novel.agent.tools.schemas import UpdateBaseInput
    from realtime_novel.agent.tools.base import ToolError
    tool = get_tool("update_base")
    input_obj = UpdateBaseInput(
        project_id=project_id, key=req.key, new_value=req.new_value
    )
    output = await tool.run(input_obj)
    if isinstance(output, ToolError):
        raise HTTPException(500, f"Update base failed: {output.message}")
    # v0.4.1 落库
    conv_id = get_or_create_conversation(user_id="default", project_id=project_id)
    result_dict = output.model_dump() if hasattr(output, "model_dump") else {"_raw": str(output)}
    record_tool_call(
        conversation_id=conv_id,
        tool_name="update_base",
        args={"project_id": project_id, "key": req.key, "new_value_preview": req.new_value[:100]},
        result=result_dict,
    )
    return UpdateBaseResponse(
        project_id=output.project_id,
        key=output.key,
        old_value_preview=output.old_value_preview,
        new_value_preview=output.new_value_preview,
        updated_at=datetime.now().isoformat(),
        chapters_affected=output.chapters_affected,
    )
