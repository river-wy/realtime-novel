"""v0.4 LLM Adapter 统一接口（v0.3 LLM 客户端已存在，不修改）

设计：
- v0.3 `realtime_novel/adapters/llm.py` 的 LLMClient 保持不变（spec §7 不重写）
- v0.4 新增本模块 LLMAdapter，对外暴露 Router + Retry + Streaming
- 所有 v0.4 业务代码（agent/tools/api）只调 LLMAdapter，不直连 LLM

对应 spec.md §5.1 + infra.md §B.2
"""
from __future__ import annotations

from typing import AsyncIterator, Callable, Awaitable, Optional

from realtime_novel.adapters.llm_router import get_router, LLMRouter
from realtime_novel.adapters.retry import with_retry, AuthenticationError
from realtime_novel.adapters.streaming import stream_with_callback
from realtime_novel.adapters.types import (
    LLMRequest, LLMResponse, LLMStreamChunk,
    ModelRole, ModelProvider,
)
from realtime_novel.adapters.providers.base import LLMProvider


class LLMAdapter:
    """v0.4 统一 LLM 调用入口（业务代码只用这个）"""

    def __init__(self, router: Optional[LLMRouter] = None):
        self.router = router or get_router()

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """同步调用（带重试）"""
        provider = self.router.get_provider(request.role)
        return await with_retry(provider.complete, request, max_retries=3, base_delay=1.0)

    async def stream(
        self, request: LLMRequest
    ) -> AsyncIterator[LLMStreamChunk]:
        """流式调用（不重试，调用方自己处理）"""
        provider = self.router.get_provider(request.role)
        async for chunk in provider.stream(request):
            yield chunk

    async def stream_with_callback(
        self,
        request: LLMRequest,
        on_chunk: Callable[[LLMStreamChunk], Awaitable[None]],
    ) -> LLMStreamChunk:
        """流式 + 回调（给 WS 推送用）"""
        provider = self.router.get_provider(request.role)
        return await stream_with_callback(provider, request, on_chunk)

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
        reference_image_url: Optional[str] = None,
    ) -> dict:
        """图片生成（Gemini 专属，走 Router fallback 路径）"""
        provider = self.router.get_provider(ModelRole.IMAGE)
        if not hasattr(provider, "generate_image"):
            raise NotImplementedError(f"Provider {provider.provider_name} does not support image generation")
        return await with_retry(
            provider.generate_image, prompt, aspect_ratio, image_size, reference_image_url,
            max_retries=3, base_delay=1.0,
        )

    def get_provider_names(self) -> list[str]:
        return self.router.get_provider_names()


# 全局单例
_adapter: Optional[LLMAdapter] = None


def get_llm_adapter() -> LLMAdapter:
    """获取全局 LLMAdapter 单例"""
    global _adapter
    if _adapter is None:
        _adapter = LLMAdapter()
    return _adapter


def reset_llm_adapter() -> None:
    """重置（测试用）"""
    global _adapter
    _adapter = None
