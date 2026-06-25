"""event_bus — 轻量异步事件总线

设计原则：
- 零第三方依赖，纯 asyncio
- handler 全部异步，emit 后立即返回（fire-and-forget）
- 保存 task 引用，防止被 GC 提前回收（官方文档警告）
- handler 异常不影响调用方，统一打 ERROR 日志

用法：
    # 注册（通常在模块顶层，import 时执行）
    @event_bus.on("onboarding.step4_confirmed")
    async def my_handler(project_id: str, **kwargs):
        ...

    # 触发（在业务逻辑里）
    await event_bus.emit("onboarding.step4_confirmed", project_id="world-xxx", payload={...})
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine, Dict, List, Set

log = logging.getLogger(__name__)

# handler 类型：接受任意 kwargs 的 async 函数
AsyncHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """轻量异步事件总线（全局单例）"""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[AsyncHandler]] = defaultdict(list)
        # 保存正在运行的 task 引用，防止被 GC 提前取消
        self._running_tasks: Set[asyncio.Task] = set()

    def on(self, event: str) -> Callable[[AsyncHandler], AsyncHandler]:
        """装饰器：注册事件 handler

        @event_bus.on("onboarding.step4_confirmed")
        async def handler(project_id: str, **kwargs): ...
        """

        def decorator(fn: AsyncHandler) -> AsyncHandler:
            self._handlers[event].append(fn)
            log.debug("EventBus: registered handler %s.%s for '%s'",
                      fn.__module__, fn.__qualname__, event)
            return fn

        return decorator

    def register(self, event: str, handler: AsyncHandler) -> None:
        """编程式注册（非装饰器场景）"""
        self._handlers[event].append(handler)
        log.debug("EventBus: registered handler %s.%s for '%s'",
                  handler.__module__, handler.__qualname__, event)

    async def emit(self, event: str, **kwargs: Any) -> None:
        """触发事件，为每个 handler 创建独立后台 Task

        立即返回，handler 在后台并发运行，不阻塞调用方。
        Task 引用保存在 _running_tasks，完成后自动移除。
        """
        handlers = self._handlers.get(event)
        if not handlers:
            log.debug("EventBus: emit '%s' — no handlers registered", event)
            return

        for handler in handlers:
            task = asyncio.create_task(self._safe_run(event, handler, **kwargs))
            self._running_tasks.add(task)
            task.add_done_callback(self._running_tasks.discard)

        log.debug("EventBus: emit '%s' — %d handler(s) dispatched", event, len(handlers))

    async def _safe_run(self, event: str, handler: AsyncHandler, **kwargs: Any) -> None:
        """包裹 handler 执行，捕获异常并打 ERROR 日志"""
        try:
            await handler(**kwargs)
        except Exception:
            log.error(
                "EventBus: handler %s.%s for event '%s' raised an exception",
                handler.__module__, handler.__qualname__, event,
                exc_info=True,
            )

    def handler_count(self, event: str) -> int:
        """返回指定事件的 handler 数量（测试用）"""
        return len(self._handlers.get(event, []))


# 全局单例
event_bus = EventBus()
