"""DeepSeek Provider（经 friday 代理 OpenAI 兼容 + Thinking 模式）

对应 infra.md §B.2.5
v0.7 改造：provider_name 加 friday/ 前缀表示提供方，api_key 走 config_loader (.llm_api_key)
"""
from __future__ import annotations

import time
from typing import AsyncIterator

from openai import AsyncOpenAI

from backend.adapters.providers.base import LLMProvider
from backend.adapters.types import LLMRequest, LLMResponse, LLMStreamChunk, ModelProvider
from backend.config.config_loader import load_llm_api_key, get_model_config


class DeepSeekProvider(LLMProvider):
    """friday/deepseek-v4-pro-tencent（经 friday 代理 OpenAI 兼容协议）"""

    provider_name = "friday/deepseek-v4-pro-tencent"
    supported_roles = ["text"]

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        # v0.7: api_key 走 .llm_api_key 文件，base_url 从 agents.json 读
        self.api_key = api_key or load_llm_api_key()
        model_cfg = get_model_config("friday/deepseek-v4-pro-tencent")
        self.base_url = base_url or model_cfg["base_url"]
        self.model = model_cfg["model_id"]  # "deepseek-v4-pro-tencent"（去掉 friday/ 前缀的真实 model id）
        self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        # default_params
        self.default_params = model_cfg.get("default_params", {})

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
        # v0.8.1: 透传探索度参数 (frequency/presence penalty)
        if request.frequency_penalty:
            kwargs["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty:
            kwargs["presence_penalty"] = request.presence_penalty
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
        stream_kwargs = {
            "model": self.model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
            "extra_body": {"thinking": {"type": "enabled"}},  # Thinking 模式
        }
        # v0.8.1: 流式也支持 frequency/presence penalty
        if request.frequency_penalty:
            stream_kwargs["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty:
            stream_kwargs["presence_penalty"] = request.presence_penalty
        stream = await self.client.chat.completions.create(**stream_kwargs)
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
