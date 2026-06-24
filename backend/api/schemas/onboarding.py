"""Onboarding 相关 Pydantic Schema

包含：
- HTTP 端点用的 Step1-5 Payload / Request / Response
- WS 端点用的 Onboarding 事件（已在 events.py 中定义，此处重新导出）
- _validate_onboarding_payload 校验工具函数
"""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Union


# ============ Step Payload ============

class OnboardingPayloadStep1(BaseModel):
    """Step 1 必选标签 (题材/风格/基调)"""
    genres: List[str] = Field(min_length=1, description="题材, 至少 1 个")
    styles: List[str] = Field(min_length=1, description="风格, 至少 1 个")
    tone: List[str] = Field(min_length=1, description="基调, 至少 1 个")


class OnboardingPayloadStep2(BaseModel):
    """Step 2 UI 主题色 (调色板, 渲染阅读页用, **不**影响世界树)"""
    palette: str = Field(default="", min_length=0, max_length=500, description="主题色, 单选, 可空")


class OnboardingPayloadStep3(BaseModel):
    """Step 3 故事引擎 (Agent 引导式填入)"""
    story_core: str = Field(default="", description="故事内核: 100+ 章体量, 主角是谁 + 场景/环境 + 做什么 + 遇到什么意外 + 留悬念")
    characters: str = Field(default="", description="主要角色: 主角/对手/盟友, 每行 '名字 - 身份/角色 - 特点/目的'")
    opening_scene: str = Field(default="", description="开篇场景: 场景 + 主角不可逆选择")


class OnboardingPayloadStep4(BaseModel):
    """Step 4 故事路径 (Agent 引导式填入)"""
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


# ============ HTTP Request / Response ============

class OnboardingRequest(BaseModel):
    step: Literal["1", "2", "3", "4", "5"]
    payload: dict = Field(default_factory=dict)


class OnboardingResponse(BaseModel):
    step: str
    result: dict
    next_step: Optional[str] = None


# ============ 校验工具 ============

def validate_onboarding_payload(step: str, payload: dict) -> dict:
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

