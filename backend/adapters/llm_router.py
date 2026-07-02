"""LLM Router: 按 model_name 选 provider + fallback

不再写死 primary_map，从 agents.json 的 models 池查 provider
"""
from __future__ import annotations

from typing import Optional

from backend.adapters.providers.base import LLMProvider
from backend.adapters.types import ModelProvider
from backend.config.config_loader import load_agents_config


class LLMRouter:
    """根据 model_name 选 provider，支持 fallback

    路由表构造逻辑：
    - 读 agents.json 的 models 字典
    - 对每个 model 字段（如 friday/deepseek-v4-pro-tencent）构造对应 Provider
    - 记录 model_name → ModelProvider 映射
    - 调用 get_provider(model_name) 时按映射返回
    """

    # model_name → ModelProvider enum 映射
    # 从 agents.json 自动构建，但保留静态映射作为 fallback（保证启动期也能工作）
    _MODEL_TO_PROVIDER = {
        "friday/deepseek-v4-pro-tencent": ModelProvider.DEEPSEEK,
        "friday/gemini-3.1-flash-image-preview": ModelProvider.GEMINI,
    }

    def __init__(self, providers: dict[ModelProvider, LLMProvider]):
        self.providers = providers

    def get_provider_by_name(self, model_name: str) -> LLMProvider:
        """根据 model_name（如 "friday/deepseek-v4-pro-tencent"）查 provider"""
        # 1. 静态映射查 ModelProvider enum
        provider_enum = self._MODEL_TO_PROVIDER.get(model_name)
        if provider_enum is None:
            # 2. fallback: 遍历 providers 字典匹配 provider_name
            for prov in self.providers.values():
                if prov.provider_name == model_name:
                    return prov
            raise RuntimeError(
                f"未找到 model={model_name!r} 对应的 provider\n"
                f"  已知 models: {list(self._MODEL_TO_PROVIDER.keys())}"
            )
        provider = self.providers.get(provider_enum)
        if provider is None:
            raise RuntimeError(f"ModelProvider={provider_enum.value} 未注册到 router")
        return provider

    def get_provider(self, role):
        """保留旧接口（向后兼容）：根据 role 选 provider"""
        from backend.adapters.types import ModelRole
        if role == ModelRole.TEXT:
            return self.get_provider_by_name(ModelProvider.DEEPSEEK.value)
        elif role == ModelRole.IMAGE:
            return self.get_provider_by_name(ModelProvider.GEMINI.value)
        else:
            raise RuntimeError(f"Unknown role: {role}")

    def get_provider_names(self) -> list[str]:
        """列出所有已注册的 provider 名称（供 /api/info 使用）"""
        return [p.provider_name for p in self.providers.values()]


# 全局单例
_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    """获取全局 Router（首次调用时用 agents.json 自动构造）"""
    global _router
    if _router is None:
        from backend.adapters.providers.deepseek import DeepSeekProvider
        from backend.adapters.providers.gemini import GeminiProvider

        # 从 agents.json 读 model 池，按需实例化 provider
        cfg = load_agents_config()
        models = cfg["models"]

        providers: dict[ModelProvider, LLMProvider] = {}
        for model_name in models:
            if model_name == "friday/deepseek-v4-pro-tencent":
                providers[ModelProvider.DEEPSEEK] = DeepSeekProvider()
            elif model_name == "friday/gemini-3.1-flash-image-preview":
                providers[ModelProvider.GEMINI] = GeminiProvider()
            # 未来接 deepseek/xxx 原生 /minimax/xxx 时，在这里加 elif

        _router = LLMRouter(providers)
    return _router


def reset_router() -> None:
    """重置 Router（测试用）"""
    global _router
    _router = None
