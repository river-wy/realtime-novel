"""v0.4 系统接口（health + info）

对应 infra.md §B.4
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from backend.adapters import get_llm_adapter

router = APIRouter(prefix="/api", tags=["system"])


class HealthResponse(BaseModel):
    status: str = "ok"
    timestamp: str
    version: str = "v0.4"


class InfoResponse(BaseModel):
    version: str
    api_version: str = "v0.4"
    llm_providers: list[str]
    modules: int = 11


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """健康检查（v0.3 移出到独立文件）"""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="v0.4",
    )


@router.get("/info", response_model=InfoResponse)
async def info() -> InfoResponse:
    """版本 + LLM provider 列表"""
    adapter = get_llm_adapter()
    return InfoResponse(
        version="v0.4.0",
        api_version="v0.4",
        llm_providers=adapter.get_provider_names(),
        modules=11,
    )
