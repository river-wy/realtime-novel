"""realtime_novel.adapters 包入口

v0.6: v0.3 adapters/llm.py 已删除，所有 LLM 调用走 LLMAdapter (v0.4+)
- DeepSeek Provider (text, OpenAI 兼容 + Thinking)
- Gemini Provider (image, Google 原生异步 submit+poll)
- Router (按 role 路由 + fallback)
- Retry (指数退避)
- Streaming (流式回调)
- types.py (LLMRequest, LLMResponse, LLMStreamChunk)
"""
from realtime_novel.adapters.types import (
    LLMRequest, LLMResponse, LLMStreamChunk, ModelRole, ModelProvider,
)
from realtime_novel.adapters.providers.base import LLMProvider
from realtime_novel.adapters.providers.deepseek import DeepSeekProvider
from realtime_novel.adapters.providers.gemini import GeminiProvider
from realtime_novel.adapters.llm_router import LLMRouter, get_router, reset_router
from realtime_novel.adapters.retry import with_retry, AuthenticationError, RateLimitError
from realtime_novel.adapters.streaming import stream_with_callback
from realtime_novel.adapters.llm_adapter import LLMAdapter, get_llm_adapter, reset_llm_adapter

__all__ = [
    # types
    "LLMRequest", "LLMResponse", "LLMStreamChunk", "ModelRole", "ModelProvider",
    # providers
    "LLMProvider", "DeepSeekProvider", "GeminiProvider",
    # router
    "LLMRouter", "get_router", "reset_router",
    # retry + streaming
    "with_retry", "AuthenticationError", "RateLimitError", "stream_with_callback",
    # main entry
    "LLMAdapter", "get_llm_adapter", "reset_llm_adapter",
]
