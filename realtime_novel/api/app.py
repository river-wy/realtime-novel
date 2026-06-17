"""v0.4 FastAPI 入口（Phase 1-4 全注册）

Phase 1: system_routes（health + info）
Phase 2-3: ws_channel（WS /api/chat）
Phase 4: http_routes（12 个 RESTful 端点）
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from realtime_novel.api.system_routes import router as system_router
from realtime_novel.api.ws_manager import router as ws_router
from realtime_novel.api.project_routes import router as project_router
from realtime_novel.api.chapter_routes import router as chapter_router
from realtime_novel.api.action_routes import router as action_router

# === FastAPI app ===

app = FastAPI(
    title="realtime-novel API",
    description="实时生成 + 可干预小说产品 · 后端 API",
    version="0.4.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有路由
app.include_router(system_router)
app.include_router(project_router)
app.include_router(chapter_router)
app.include_router(action_router)
app.include_router(ws_router)


def create_app() -> FastAPI:
    """工厂函数（供测试 fixtures 用）"""
    return app
