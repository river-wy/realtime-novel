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

    def __init__(self, api_key: str | None = None, base_url: str = "https://aigc.sankuai.com/v1/openai/native"):
        # friday 平台只用一个 Bearer token (app_id 即 api_key)
        # 环境变量统一命名 FRIDAY_API_KEY (与 config.yaml app_id 字段语义对齐)
        self.api_key = api_key or os.environ.get("FRIDAY_API_KEY", "")
        if not self.api_key:
            raise ValueError("FRIDAY_API_KEY environment variable not set")
        self.client = AsyncOpenAI(base_url=base_url, api_key=self.api_key)
        self.model = "deepseek-v4-pro-tencent"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """同步调用（关 thinking，节省时间）"""
        start = time.time()
        kwargs = {
            "model": self.model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        # v0.6 新增：response_format 透传（强制 JSON 输出）
        if request.response_format:
            kwargs["response_format"] = request.response_format
        response = await self.client.chat.completions.create(**kwargs)
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
        """构建 messages 数组

        v0.4.1 优先用 messages 字段（多轮对话）：
        - 如果 request.messages 非空：直接用 + 补 system_prompt（如果不存在）
        - 如果 request.messages 空：兼容旧代码（system_prompt + prompt 拼成单条 user）
        """
        msgs = []

        if request.messages:
            # 多轮模式：直接用 messages 数组
            msgs.extend(request.messages)
            # 如果传了 system_prompt 且 messages 里没有 system，拼到首位
            if request.system_prompt and not any(m.get("role") == "system" for m in msgs):
                msgs.insert(0, {"role": "system", "content": request.system_prompt})
        else:
            # 兼容模式：单条 user
            if request.system_prompt:
                msgs.append({"role": "system", "content": request.system_prompt})
            if request.prompt:
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
