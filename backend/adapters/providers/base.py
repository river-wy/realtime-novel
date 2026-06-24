"""LLM Provider Protocol 抽象

对应 infra.md §B.2.1
"""
from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from backend.adapters.types import LLMRequest, LLMResponse, LLMStreamChunk


@runtime_checkable
class LLMProvider(Protocol):
    """所有 LLM Provider 必须实现的接口"""

    provider_name: str  # "deepseek-v4-pro-tencent" | "gemini-3.1-flash-image-preview"
    supported_roles: list[str]  # ["text"] | ["image"] | ["text", "image"]

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """同步调用：等待完整响应"""
        ...

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """流式调用：逐 chunk 输出"""
        ...

    def is_available(self) -> bool:
        """Provider 是否可用（用于 fallback）"""
        ...

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
        reference_image_url: str | None = None,
    ) -> dict:
        """图片生成（image role 专属，text-only Provider 应 raise NotImplementedError）

        注意：此方法仅对 ModelRole.IMAGE 的 Provider（如 GeminiProvider）有意义。
        text-only Provider（如 DeepSeekProvider）实现时直接 raise NotImplementedError 即可。
        TODO: 未来接入更多 image provider 时，可将此方法拆出单独的 ImageProvider Protocol。
        """
        ...
