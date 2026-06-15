"""api/app.py — FastAPI 入口（M-ε.0 阶段 stub）

M-ε 启动 (2026-06-15) 后, realtime-novel 的 CLI 之外新增 HTTP API 入口:
- realtime-novel-api 命令启动 uvicorn
- 默认端口 8080 (配置见 pyproject.toml [tool.uvicorn])
- 路由在 M-ε.5 实装 (routers/*.py)

M-ε.0 阶段: 仅建骨架 + health check 端点
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


# === FastAPI app 单例 ===

app = FastAPI(
    title="realtime-novel API",
    description="实时生成 + 可干预小说产品 · 后端 API",
    version="0.4.0-alpha",  # M-ε 启动后
)


# CORS (M-ε.5 frontend/ 实装后, 需要允许 http://localhost:5173 跨域)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # M-ε.5 时收紧到 vite dev server 实际地址
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Health check 端点 (M-ε.0 阶段唯一可调端点) ===

@app.get("/api/health")
async def health() -> dict:
    """健康检查 — 验证后端进程 + 包 import 正常"""
    import realtime_novel
    return {
        "status": "ok",
        "version": realtime_novel.__version__,
        "stage": "M-ε.0 (骨架准备)",
    }


@app.get("/api/info")
async def info() -> dict:
    """工程信息 — 5 子包 + CLI + LLM 配置"""
    import realtime_novel
    return {
        "package": "realtime_novel",
        "version": realtime_novel.__version__,
        "structure": {
            "core": "数据模型 (7 件 Schema + WorldTree + ProjectManager + exceptions)",
            "services": "业务服务 (S1-S5 orchestrators)",
            "adapters": "外部依赖 (LLM / Prompt / IO / 算法)",
            "cli": "命令行 (argparse 4 子命令, deprecated)",
            "api": "HTTP API (M-ε.5 实装)",
            "utils": "工具类",
        },
        "routers": {
            "projects": "M-ε.5 实装",
            "chapters": "M-ε.5 实装",
            "onboarding": "M-ε.5 实装",
            "intervention": "M-ε.5 实装",
            "rollback": "M-ε.5 实装",
        },
    }


# === 启动入口 (供 realtime-novel-api 命令调用) ===

def run() -> None:
    """realtime-novel-api 命令入口
    配置读 pyproject.toml [tool.uvicorn] 段
    """
    import uvicorn
    host = os.environ.get("REALTIME_NOVEL_HOST", "127.0.0.1")
    port = int(os.environ.get("REALTIME_NOVEL_PORT", "8080"))
    log_level = os.environ.get("REALTIME_NOVEL_LOG_LEVEL", "info")

    uvicorn.run(
        "realtime_novel.api.app:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=False,  # M-ε.5 后改 True for dev
    )
