"""指数退避重试 + 异常分类

对应 infra.md §B.2.4
"""
from __future__ import annotations

import asyncio
from typing import TypeVar, Callable, Awaitable

T = TypeVar("T")


# 不重试的异常（鉴权/配置错误）
class AuthenticationError(Exception):
    """鉴权失败，不重试"""
    pass


# 重试的异常（限流/网络/超时）
class RateLimitError(Exception):
    """限流，可重试 + 退避"""
    pass


async def with_retry(
    func: Callable[..., Awaitable[T]],
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs,
) -> T:
    """指数退避重试：1s → 2s → 4s

    AuthenticationError 立即抛（不重试）
    RateLimitError 重试 + 退避
    其他 Exception 重试 + 退避
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except AuthenticationError:
            raise  # 鉴权失败立即抛
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
    if last_error:
        raise last_error
    raise RuntimeError("with_retry: no attempts made")
