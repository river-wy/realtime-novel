"""v0.4 FastAPI 入口（Phase 1-4 全注册）

Phase 1: system_routes（health + info）
Phase 2-3: ws_channel（WS /api/chat）
Phase 4: http_routes（12 个 RESTful 端点）
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# v0.8.3: 初始化日志 (在 import 其他模块前调, 让后续 logger 接管)
from backend.utils.logger import configure_logging

configure_logging()

from backend.api.system_routes import router as system_router
from backend.api.ws_manager import router as ws_router
from backend.api.project_routes import router as project_router
from backend.api.chapter_routes import router as chapter_router
from backend.api.action_routes import router as action_router
from backend.api.onboarding_routes import router as onboarding_router

# 触发领域事件 handler 注册（import 即注册，无需显式调用）
import backend.agent.onboarding.hooks  # noqa: F401

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
app.include_router(onboarding_router)
app.include_router(action_router)
app.include_router(ws_router)

# v0.9: 静态文件服务（封面图等）
# /static/projects/{project_id}/cover.png → data/projects/{project_id}/cover.png
_PROJECTS_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "projects"
_PROJECTS_DATA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/projects", StaticFiles(directory=str(_PROJECTS_DATA_DIR)), name="project-static")


def create_app() -> FastAPI:
    """工厂函数（供测试 fixtures 用）"""
    return app
