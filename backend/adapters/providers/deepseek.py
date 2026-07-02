"""DeepSeek Provider（经 friday 代理 OpenAI 兼容 + Thinking 模式）

对应 infra.md §B.2.5
"""
from __future__ import annotations

import time
from openai import AsyncOpenAI
from typing import AsyncIterator

from backend.adapters.providers.base import LLMProvider
from backend.adapters.types import LLMRequest, LLMResponse, LLMStreamChunk, ModelProvider, ToolCall, ToolCallFunction
from backend.config.config_loader import load_llm_api_key, get_model_config
from backend.utils.logger import logger


@logger
class DeepSeekProvider(LLMProvider):
    """friday/deepseek-v4-pro-tencent（经 friday 代理 OpenAI 兼容协议）"""

    provider_name = "friday/deepseek-v4-pro-tencent"
    supported_roles = ["text"]

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        # api_key 走 .llm_api_key 文件，base_url 从 agents.json 读
        self.api_key = api_key or load_llm_api_key()
        model_cfg = get_model_config("friday/deepseek-v4-pro-tencent")
        self.base_url = base_url or model_cfg["base_url"]
        self.model = model_cfg["model_id"]  # "deepseek-v4-pro-tencent"（去掉 friday/ 前缀的真实 model id）
        self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        # default_params
        self.default_params = model_cfg.get("default_params", {})

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """同步调用（流式聚合，兼容 DeepSeek thinking 模式 content 返空问题）

        DeepSeek v4-pro thinking 模式下非流式调用 content 始终为空，
        答案在 reasoning_content 里且容易被 max_tokens 截断。
        改用流式聚合 content delta，与 stream() 行为一致。
        """
        start = time.time()
        msg_count = len(request.messages or [])
        est_tokens = int(sum(len(m.get("content") or "") for m in (request.messages or [])) * 0.4)
        self.log.info("LLM complete START: model=%s, temp=%.2f, max_tokens=%d, thinking=%s, msg_count=%d, est_input_tokens~=%d",
                 self.model, request.temperature, request.max_tokens,
                 request.enable_thinking, msg_count, est_tokens)
        # enable_thinking=False 时关闭 thinking（防止 reasoning token 占用 max_tokens）
        thinking_body = {"thinking": {"type": "enabled"}} if request.enable_thinking else {"thinking": {"type": "disabled"}}
        stream_kwargs = {
            "model": self.model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
            "extra_body": thinking_body,
        }
        # response_format 透传（强制 JSON 输出）
        if request.response_format:
            stream_kwargs["response_format"] = request.response_format
        # 透传探索度参数 (frequency/presence penalty)
        if request.frequency_penalty:
            stream_kwargs["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty:
            stream_kwargs["presence_penalty"] = request.presence_penalty
        # 透传 tools / tool_choice（OpenAI function calling）
        if request.tools:
            stream_kwargs["tools"] = request.tools
        if request.tool_choice is not None:
            stream_kwargs["tool_choice"] = request.tool_choice

        content_parts = []
        # tool_calls 流式累积（OpenAI 协议按 fragment 返回）
        tool_calls_accumulator: dict[int, dict] = {}
        input_tokens = 0
        output_tokens = 0
        finish_reason = None
        stream = await self.client.chat.completions.create(**stream_kwargs)
        async for chunk in stream:
            if not chunk.choices:
                # usage 汇总 chunk（无 choices）
                if hasattr(chunk, "usage") and chunk.usage:
                    input_tokens = getattr(chunk.usage, "prompt_tokens", 0)
                    output_tokens = getattr(chunk.usage, "completion_tokens", 0)
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
            # 累积 tool_calls fragments
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_accumulator:
                        tool_calls_accumulator[idx] = {
                            "id": tc_delta.id or "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    acc = tool_calls_accumulator[idx]
                    if tc_delta.id:
                        acc["id"] = tc_delta.id
                    if hasattr(tc_delta, "function") and tc_delta.function:
                        if tc_delta.function.name:
                            acc["function"]["name"] = (
                                acc["function"].get("name", "") + tc_delta.function.name
                                if acc["function"].get("name") and not tc_delta.function.name.startswith(acc["function"]["name"])
                                else tc_delta.function.name
                            )
                            # 简化：直接覆盖（OpenAI protocol name 一般一次发完）
                            acc["function"]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            acc["function"]["arguments"] += tc_delta.function.arguments
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

        duration_ms = int((time.time() - start) * 1000)
        content = "".join(content_parts)
        # 转 ToolCall 列表
        tool_calls = None
        if tool_calls_accumulator:
            tool_calls = [
                ToolCall(
                    id=v["id"],
                    type=v["type"],
                    function=ToolCallFunction(
                        name=v["function"]["name"],
                        arguments=v["function"]["arguments"],
                    ),
                )
                for k, v in sorted(tool_calls_accumulator.items())
            ]
        self.log.info("LLM complete DONE: model=%s, input_tokens=%d, output_tokens=%d, duration_ms=%d, content_len=%d, tool_calls=%d, finish=%s",
                 self.model, input_tokens, output_tokens, duration_ms, len(content), len(tool_calls) if tool_calls else 0, finish_reason)
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            provider=ModelProvider.DEEPSEEK,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            cached=False,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """流式调用 + Thinking 模式（reasoning_content 透传）"""
        msg_count = len(request.messages or [])
        self.log.info("LLM stream START: model=%s, temp=%.2f, max_tokens=%d, thinking=%s, msg_count=%d",
                 self.model, request.temperature, request.max_tokens, request.enable_thinking, msg_count)
        # enable_thinking=False 时关闭 thinking
        thinking_body = {"thinking": {"type": "enabled"}} if request.enable_thinking else {"thinking": {"type": "disabled"}}
        stream_kwargs = {
            "model": self.model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
            "extra_body": thinking_body,
        }
        # 流式也支持 frequency/presence penalty
        if request.frequency_penalty:
            stream_kwargs["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty:
            stream_kwargs["presence_penalty"] = request.presence_penalty
        # 流式也支持 tools / tool_choice
        if request.tools:
            stream_kwargs["tools"] = request.tools
        if request.tool_choice is not None:
            stream_kwargs["tool_choice"] = request.tool_choice
        _stream_start = time.time()
        _total_chars = 0
        stream = await self.client.chat.completions.create(**stream_kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = delta.content or ""
            reasoning = getattr(delta, "reasoning_content", None) or ""
            _total_chars += len(content)
            is_final = chunk.choices[0].finish_reason is not None
            # 提取 tool_calls 增量（原始 OpenAI 格式）
            tool_calls_delta = None
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                tool_calls_delta = []
                for tc in delta.tool_calls:
                    tool_calls_delta.append({
                        "index": tc.index,
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name if tc.function else None,
                            "arguments": tc.function.arguments if tc.function else None,
                        } if tc.function else None,
                    })
            if is_final:
                self.log.info("LLM stream DONE: model=%s, duration_ms=%d, total_chars=%d, finish=%s",
                         self.model, int((time.time() - _stream_start) * 1000),
                         _total_chars, chunk.choices[0].finish_reason)
            yield LLMStreamChunk(
                delta=content,
                reasoning=reasoning,
                provider=ModelProvider.DEEPSEEK,
                is_final=is_final,
                finish_reason=chunk.choices[0].finish_reason,
                tool_calls_delta=tool_calls_delta,
            )

    def _build_messages(self, request: LLMRequest) -> list[dict]:
        """构建 messages 数组

        优先用 messages 字段（多轮对话）：
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
        """字符数估算（简化版）"""
        return len(text) // 2

    def is_available(self) -> bool:
        return True  # 简化

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
        reference_image_url: str | None = None,
    ) -> dict:
        raise NotImplementedError("DeepSeek only supports text, use GeminiProvider for images")
