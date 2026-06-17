"""v0.4 测试 fixtures + Mock LLM Provider

对应 novel-tests.json
"""
from __future__ import annotations

import os
import asyncio
import tempfile
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from realtime_novel.api.app import create_app
from realtime_novel.persistence import reset_store, get_store
from realtime_novel.adapters import reset_llm_adapter, reset_router
from realtime_novel.adapters.types import LLMRequest, LLMResponse, LLMStreamChunk, ModelProvider
from realtime_novel.adapters.providers.base import LLMProvider
from realtime_novel.agent.tools import reset_tools
from realtime_novel.agent.state_graph import reset_graph


# ============ pytest 配置 ============

# 在测试前设置环境变量（避免 import 顺序问题）
os.environ.setdefault("FRIDAY_APP_ID", "test_app_id_for_unit_tests")


# ============ temp_db fixture ============

@pytest.fixture
def temp_db(tmp_path):
    """每个测试用临时 SQLite DB（不污染真实数据）"""
    db_path = tmp_path / "test_novel.db"
    reset_store()
    store = get_store(db_path)
    yield store
    reset_store()


# ============ test_app fixture ============

@pytest_asyncio.fixture
async def test_app(temp_db):
    """FastAPI app + ASGI client"""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield app, client
    # 清理
    reset_tools()
    reset_graph()
    reset_llm_adapter()
    reset_router()


# ============ Mock LLM Provider ============

class MockLLMProvider(LLMProvider):
    """测试用 mock LLM（不调真实 friday）"""

    provider_name = "mock-llm"
    supported_roles = ["text", "image"]

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="[mock response]",
            provider=ModelProvider.DEEPSEEK,
            input_tokens=10,
            output_tokens=5,
            duration_ms=100,
            cached=False,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        for word in ["[mock ", "streamed ", "response]"]:
            yield LLMStreamChunk(
                delta=word,
                reasoning="",
                provider=ModelProvider.DEEPSEEK,
                is_final=False,
            )
        yield LLMStreamChunk(
            delta="",
            reasoning="",
            provider=ModelProvider.DEEPSEEK,
            is_final=True,
            finish_reason="stop",
        )

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
        reference_image_url: str | None = None,
    ) -> dict:
        return {
            "image_urls": ["https://mock.example.com/image.png"],
            "description": f"mock image for: {prompt}",
            "duration_ms": 100,
            "cached": False,
        }

    def is_available(self) -> bool:
        return True


@pytest.fixture
def mock_llm(monkeypatch):
    """替换 llm-adapter 为 mock"""
    from realtime_novel.adapters import get_llm_adapter
    mock = MockLLMProvider()
    # 直接替换 router 里的 provider
    adapter = get_llm_adapter()
    adapter.router.providers = {
        ModelProvider.DEEPSEEK: mock,
        ModelProvider.GEMINI: mock,
    }
    return mock
