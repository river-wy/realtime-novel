"""统一日志配置 (v0.8.3 新增)

之前散落: print() / logging.warning() / 不分模块, LLM 调用无结构化日志.
现在: 统一 logger = backend.{module}, 输出到 stderr (uvicorn 捕获) + tmp/logs/backend.log.

用法:
    from backend.utils.logger import get_logger
    log = get_logger(__name__)
    log.info("LLM 调用开始: step=%s, msg_count=%d", step, len(messages))
    log.error("LLM 输出解析失败: %s", e, exc_info=True)

设计:
    - 命名空间: backend.* (沿用 Python logging 惯例)
    - 输出: stderr (uvicorn capture) + tmp/logs/backend.log (文件, 持久化)
    - 格式: 时间 | 等级 | logger 名 | 消息
    - 级别: INFO 默认, 可通过 LOG_LEVEL=DEBUG 环境变量调
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Callable, TypeVar, overload

_C = TypeVar("_C", bound=type)
_F = TypeVar("_F", bound=Callable)

_LOG_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-5s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging() -> None:
    """全局日志初始化 (幂等). 在 main 模块入口调一次即可."""
    global _configured
    if _configured:
        return
    _configured = True

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # root logger
    root = logging.getLogger()
    root.setLevel(level)
    # 清空已有 handler (避免重复)
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # stderr handler (uvicorn 捕获, 用户在控制台看)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(level)
    stderr_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)

    # 文件 handler (tmp/logs/backend.log, 持久化)
    try:
        project_root = Path(__file__).resolve().parent.parent.parent
        log_dir = project_root / "tmp" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "backend.log", encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception as e:
        # 文件 handler 失败不阻断, stderr 还能用
        sys.stderr.write(f"[logger] file handler init failed: {e}\n")

    # uvicorn / fastapi logger 接管 (让他们的 access log 也走我们的格式)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        lg = logging.getLogger(name)
        lg.handlers = []  # 清掉 uvicorn 默认 handler
        lg.propagate = True  # 走 root


def get_logger(name: str) -> logging.Logger:
    """获取 logger (子模块用 `__name__`). 第一次调用会自动 configure."""
    if not _configured:
        configure_logging()
    return logging.getLogger(name)


@overload
def logger(target: _C) -> _C: ...
@overload
def logger(target: _F) -> _F: ...
def logger(target):
    """通用装饰器 — 同时支持类和函数，等价 Java @Slf4j

    logger 名取 {module}.{qualname}，与 get_logger(__name__) 命名空间一致。

    用法（类）:
        @logger
        class MyService:
            def do_something(self):
                self.log.info("done: %s", result)

    用法（模块级函数）:
        @logger
        async def my_func():
            my_func.log.info("called")
    """
    target.log = get_logger(f"{target.__module__}.{target.__qualname__}")
    return target
