"""DeepSeek Provider（经 friday 代理 OpenAI 兼容 + Thinking 模式）

对应 infra.md §B.2.5
对接参考: /Users/wuyu/AiTest/llm-test/friday/test_deepseek.py
"""
from __future__ import annotations

import os
import time
from typing import AsyncIterator

from openai import AsyncOpenAI

from realtime_novel.adapters.providers.base import LLMProvider
from realtime_novel.adapters.types import LLMRequest, LLMResponse, LLMStreamChunk, ModelProvider


class DeepSeekProvider(LLMProvider):
    """deepseek-v4-pro-tencent（经 friday 代理）"""

    provider_name = "deepseek-v4-pro-tencent"
    supported_roles = ["text"]

    def __init__(self, app_id: str | None = None, base_url: str = "https://aigc.sankuai.com/v1/openai/native"):
        self.app_id = app_id or os.environ.get("FRIDAY_APP_ID", "")
        if not self.app_id:
            raise ValueError("FRIDAY_APP_ID environment variable not set")
        self.client = AsyncOpenAI(base_url=base_url, api_key=self.app_id)
        self.model = "deepseek-v4-pro-tencent"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """同步调用（关 thinking，节省时间）"""
        start = time.time()
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=self._build_messages(request),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        duration_ms = int((time.time() - start) * 1000)
        return LLMResponse(
            content=response.choices[0].message.content or "",
            provider=ModelProvider.DEEPSEEK,
            input_tokens=getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
            output_tokens=getattr(response.usage, "completion_tokens", 0) if response.usage else 0,
            duration_ms=duration_ms,
            cached=False,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """流式调用 + Thinking 模式（reasoning_content 透传）"""
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=self._build_messages(request),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
            extra_body={"thinking": {"type": "enabled"}},  # Thinking 模式
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = delta.content or ""
            reasoning = getattr(delta, "reasoning_content", None) or ""
            yield LLMStreamChunk(
                delta=content,
                reasoning=reasoning,
                provider=ModelProvider.DEEPSEEK,
                is_final=chunk.choices[0].finish_reason is not None,
                finish_reason=chunk.choices[0].finish_reason,
            )

    def _build_messages(self, request: LLMRequest) -> list[dict]:
        msgs = []
        if request.system_prompt:
            msgs.append({"role": "system", "content": request.system_prompt})
        msgs.append({"role": "user", "content": request.prompt})
        return msgs

    def count_tokens(self, text: str) -> int:
        """字符数估算（v0.4 简化版）"""
        return len(text) // 2

    def is_available(self) -> bool:
        return True  # v0.4 简化

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
        reference_image_url: str | None = None,
    ) -> dict:
        raise NotImplementedError("DeepSeek only supports text, use GeminiProvider for images")
