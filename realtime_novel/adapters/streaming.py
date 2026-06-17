"""流式回调封装

对应 infra.md §B.2.4 streaming.py
"""
from __future__ import annotations

from typing import AsyncIterator, Callable, Awaitable

from realtime_novel.adapters.providers.base import LLMProvider
from realtime_novel.adapters.types import LLMRequest, LLMStreamChunk


async def stream_with_callback(
    provider: LLMProvider,
    request: LLMRequest,
    on_chunk: Callable[[LLMStreamChunk], Awaitable[None]],
) -> LLMStreamChunk:
    """流式输出 + 回调（用于 WebSocket 实时推送）

    返回最后一个 chunk（含 finish_reason）
    """
    last_chunk: LLMStreamChunk | None = None
    async for chunk in provider.stream(request):
        await on_chunk(chunk)
        last_chunk = chunk
    if last_chunk is None:
        raise RuntimeError("Provider produced no chunks")
    return last_chunk
