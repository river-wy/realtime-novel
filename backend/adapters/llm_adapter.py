"""v0.4 LLM Adapter 统一接口（v0.3 LLM 客户端已存在，不修改）

设计：
- v0.3 `backend/adapters/llm.py` 的 LLMClient 保持不变（spec §7 不重写）
- v0.4 新增本模块 LLMAdapter，对外暴露 Router + Retry + Streaming
- 所有 v0.4 业务代码（agent/tools/api）只调 LLMAdapter，不直连 LLM

对应 spec.md §5.1 + infra.md §B.2
"""
from __future__ import annotations

import os
from typing import AsyncIterator, Callable, Awaitable, Optional

from backend.adapters.llm_router import get_router, LLMRouter
from backend.adapters.retry import with_retry
from backend.adapters.streaming import stream_with_callback
from backend.adapters.types import (
    LLMRequest, LLMResponse, LLMStreamChunk,
    ModelRole, )
from backend.utils.logger import logger

# 设置环境变量 LLM_PROMPT_LOG=1 即可开启完整 prompt 打印（独立于 LOG_LEVEL）
_PROMPT_LOG_ENABLED = os.environ.get("LLM_PROMPT_LOG", "").strip() in ("1", "true", "yes")


@logger
def _log_request(request: LLMRequest) -> None:
    """在 LLM 实际调用前，打印完整上下文。
    需设置环境变量 LLM_PROMPT_LOG=1 开启，避免正常运行时刷屏。
    """
    if not _PROMPT_LOG_ENABLED:
        return

    lines = ["[LLM PROMPT] ══════════════════════════════════════════════════════"]
    lines.append(f"  role={request.role.value}  temp={request.temperature}"
                 f"  max_tokens={request.max_tokens}  thinking={request.enable_thinking}")

    if request.system_prompt:
        lines.append("  ── system ─────────────────────────────────────────────────────")
        lines.append(request.system_prompt)

    if request.messages:
        for i, msg in enumerate(request.messages):
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
                # tool_result / multipart content 格式
                content = " | ".join(
                    (part.get("text") or str(part)) for part in content
                )
            lines.append(f"  ── [{i}] {role} ───────────────────────────────────────────")
            lines.append(str(content))
    elif request.prompt:
        lines.append("  ── prompt ──────────────────────────────────────────────────────")
        lines.append(request.prompt)

    lines.append("════════════════════════════════════════════════════════════════")
    _log_request.log.info("\n".join(lines))


@logger
class LLMAdapter:
    """v0.4 统一 LLM 调用入口（业务代码只用这个）"""

    def __init__(self, router: Optional[LLMRouter] = None):
        self.router = router or get_router()

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """同步调用（带重试）"""
        provider = self.router.get_provider(request.role)
        _log_request(request)
        return await with_retry(provider.complete, request, max_retries=3, base_delay=1.0)

    async def complete_with_messages(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        role: ModelRole = ModelRole.TEXT,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        enable_thinking: bool = True,
    ) -> LLMResponse:
        """v0.4.1 新增：多轮对话便捷调用 (v0.8.1 加 frequency/presence penalty)

        Args:
            messages: OpenAI 格式 messages 数组（不含 system）
                [{"role": "user", "content": "..."}, ...]
            system_prompt: system prompt（可选）
            temperature/max_tokens/role: 其他参数
            frequency_penalty/presence_penalty: v0.8.1 探索度旋钮用
                - frequency_penalty: 正值减少重复用词 (OpenAI 标准参数)
                - presence_penalty:  正值鼓励新话题 (OpenAI 标准参数)
            enable_thinking: v0.8.2 是否启用 thinking 模式（DeepSeek）；summary/分类等轻量任务可设 False
        """
        request = LLMRequest(
            prompt="",  # messages 模式下不需要
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            role=role,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            enable_thinking=enable_thinking,
        )
        return await self.complete(request)

    async def stream(
        self, request: LLMRequest
    ) -> AsyncIterator[LLMStreamChunk]:
        """流式调用（不重试，调用方自己处理）"""
        provider = self.router.get_provider(request.role)
        _log_request(request)
        async for chunk in provider.stream(request):
            yield chunk

    async def stream_with_callback(
        self,
        request: LLMRequest,
        on_chunk: Callable,
    ) -> LLMStreamChunk:
        """流式 + 回调（给 WS 推送用）"""
        provider = self.router.get_provider(request.role)
        _log_request(request)
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
