"""Action 路由（5 个：onboarding/interventions/rollback/image/base PATCH）

对应 api.md §B.3
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Union
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

class OnboardingPayloadStep1(BaseModel):
    """Step 1 必选标签 (题材/风格/基调)"""
    genres: List[str] = Field(min_length=1, description="题材, 至少 1 个")
    styles: List[str] = Field(min_length=1, description="风格, 至少 1 个")
    tone: List[str] = Field(min_length=1, description="基调, 至少 1 个")


class OnboardingPayloadStep2(BaseModel):
    """Step 2 UI 主题色 (调色板, 渲染阅读页用, **不**影响世界树)

    v0.7: 改为单选 str（一个项目对应一个主题色）
    - 前端 selectPalette() 发 string | null
    - 后端落库到 projects.palette (str, max_length=500)
    """
    palette: str = Field(default="", min_length=0, max_length=500, description="主题色, 单选, 可空")


class OnboardingPayloadStep3(BaseModel):
    """Step 3 故事引擎 (Agent 引导式填入) — v0.7 重构

    从 4 字段 (核心关系/情感锚点/禁区/结局偏好) 精简为 3 字段:
    - story_core: 故事内核 (主角要做什么 + 什么阻止)
    - characters: 主要角色 (主角/对手/盟友, 每行 '名字-要什么-怕什么')
    - opening_scene: 开篇场景 (场景描述 + 主角那一刻的不可逆选择)
    """
    story_core: str = Field(default="", description="故事内核: 主角要做什么 + 什么阻止")
    characters: str = Field(default="", description="主要角色: 主角/对手/盟友, 每行 '名字-要什么-怕什么'")
    opening_scene: str = Field(default="", description="开篇场景: 场景 + 主角不可逆选择")


class OnboardingPayloadStep4(BaseModel):
    """Step 4 故事路径 (Agent 引导式填入) — v0.7 重构

    从 4 字段 (主线/支线/人物/种子) 改为 4 字段:
    - main_arc: 主线节点 (3-5 个剧情转折, 每行 1 个)
    - sub_plots: 支线 (每行 1 个)
    - seeds: 种子/钩子 (第 1 章埋什么, N 章后亮出来)
    - reader_feeling: 读者情绪 (希望读者合上书那一刻心里留下什么)

    去掉「人物」字段 (Step 3 已填)
    砍掉 v0.5 的「禁区」「结局偏好」
    """
    main_arc: str = Field(default="", description="主线节点, 3-5 个剧情转折, 每行 1 个")
    sub_plots: str = Field(default="", description="支线, 每行 1 个")
    seeds: str = Field(default="", description="种子/钩子, 每行 1 个")
    reader_feeling: str = Field(default="", description="读者情绪, 希望读者读完后心里留下什么")


class OnboardingPayloadStep5(BaseModel):
    """Step 5 生成第 1 章 (无可选 payload)"""
    pass


# Discriminated union (按 step 区分)
OnboardingPayload = Union[
    OnboardingPayloadStep1,
    OnboardingPayloadStep2,
    OnboardingPayloadStep3,
    OnboardingPayloadStep4,
    OnboardingPayloadStep5,
]


def _validate_onboarding_payload(step: str, payload: dict) -> dict:
    """按 step 校验 payload (Pydantic 强类型)

    Raises:
        HTTPException 422: 字段缺失/类型错
    """
    payload_map = {
        "1": OnboardingPayloadStep1,
        "2": OnboardingPayloadStep2,
        "3": OnboardingPayloadStep3,
        "4": OnboardingPayloadStep4,
        "5": OnboardingPayloadStep5,
    }
    schema_cls = payload_map.get(step)
    if not schema_cls:
        raise HTTPException(400, f"Unknown step: {step}")
    try:
        validated = schema_cls.model_validate(payload)
        return validated.model_dump()
    except Exception as e:
        raise HTTPException(422, f"Step {step} payload 校验失败: {e}")


class OnboardingRequest(BaseModel):
    step: Literal["1", "2", "3", "4", "5"]
    payload: dict = Field(default_factory=dict)


class OnboardingResponse(BaseModel):
    step: str
    result: dict
    next_step: Optional[str] = None


@router.post("/{project_id}/onboarding", response_model=OnboardingResponse)
async def onboarding(project_id: str, req: OnboardingRequest):
    """5 步启动链路（v0.4.1 落库）

    m-v0.5-onboarding s1.5: payload Pydantic schema 校验
    """
    # s1.5: 强类型校验 (按 step 区分)
    validated_payload = _validate_onboarding_payload(req.step, req.payload)

    try:
        result = await _onboarding.step(project_id, req.step, validated_payload)
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
        project_id=project_id,
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
        project_id=project_id,
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
