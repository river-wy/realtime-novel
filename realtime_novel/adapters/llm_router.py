"""LLM Router: 按 model_role 选 provider + fallback

对应 infra.md §B.2.3
"""
from __future__ import annotations

from typing import Optional

from realtime_novel.adapters.providers.base import LLMProvider
from realtime_novel.adapters.types import ModelRole, ModelProvider


class LLMRouter:
    """根据 role 选 provider，支持 fallback"""

    def __init__(self, providers: dict[ModelProvider, LLMProvider]):
        self.providers = providers

    def get_provider(self, role: ModelRole) -> LLMProvider:
        """主选 + fallback"""
        primary_map = {
            ModelRole.TEXT: ModelProvider.DEEPSEEK,
            ModelRole.IMAGE: ModelProvider.GEMINI,
        }
        primary = primary_map[role]
        provider = self.providers.get(primary)
        if provider is not None and provider.is_available():
            return provider
        # fallback：反向选
        fallback_map = {
            ModelProvider.DEEPSEEK: ModelProvider.GEMINI,
            ModelProvider.GEMINI: ModelProvider.DEEPSEEK,
        }
        fallback = fallback_map[primary]
        fallback_provider = self.providers.get(fallback)
        if fallback_provider is not None:
            return fallback_provider
        raise RuntimeError(f"No available provider for role={role.value}")

    def get_provider_names(self) -> list[str]:
        """列出所有已注册的 provider 名称（供 /api/info 使用）"""
        return [p.provider_name for p in self.providers.values()]


# 全局单例
_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    """获取全局 Router（首次调用时用默认 provider 初始化）"""
    global _router
    if _router is None:
        from realtime_novel.adapters.providers.deepseek import DeepSeekProvider
        from realtime_novel.adapters.providers.gemini import GeminiProvider
        _router = LLMRouter({
            ModelProvider.DEEPSEEK: DeepSeekProvider(),
            ModelProvider.GEMINI: GeminiProvider(),
        })
    return _router


def reset_router() -> None:
    """重置 Router（测试用）"""
    global _router
    _router = None
