"""Gemini Provider（friday 代理 Google 原生异步 submit + poll）

对应 infra.md §B.2.6
对接参考: /Users/wuyu/AiTest/llm-test/friday/test_gemini.py
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import AsyncIterator

import httpx

from realtime_novel.adapters.providers.base import LLMProvider
from realtime_novel.adapters.types import (
    LLMRequest, LLMResponse, LLMStreamChunk, ModelProvider,
)


class GeminiProvider(LLMProvider):
    """gemini-3.1-flash-image-preview（经 friday 代理 Google 原生异步协议）"""

    provider_name = "gemini-3.1-flash-image-preview"
    supported_roles = ["image"]

    SUBMIT_URL = "https://aigc.sankuai.com/v1/google/models/gemini-3.1-flash-image-preview:imageGenerate"
    QUERY_URL_TEMPLATE = "https://aigc.sankuai.com/v1/google/models/{operation_id}:imageGenerateQuery"

    POLL_INTERVAL = 3       # 轮询间隔（秒）
    POLL_TIMEOUT = 120      # 轮询超时（秒）

    def __init__(self, api_key: str | None = None):
        # friday 平台只用一个 Bearer token (app_id 即 api_key)
        # 环境变量统一命名 FRIDAY_API_KEY (与 config.yaml app_id 字段语义对齐)
        self.api_key = api_key or os.environ.get("FRIDAY_API_KEY", "")
        if not self.api_key:
            raise ValueError("FRIDAY_API_KEY environment variable not set")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
        reference_image_url: str | None = None,
    ) -> dict:
        """异步提交图片生成任务 + 轮询，返回 {image_urls, description, cached, duration_ms}"""
        start = time.time()
        parts = [{"text": prompt}]
        if reference_image_url:
            parts.append({
                "file_data": {
                    "mime_type": "image/png",
                    "file_uri": reference_image_url,
                }
            })

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": aspect_ratio, "imageSize": image_size},
            },
        }

        async with httpx.AsyncClient(timeout=60) as client:
            # Step 1: 提交任务
            resp = await client.post(self.SUBMIT_URL, headers=self.headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Gemini submit failed: {resp.status_code} {resp.text[:200]}"
                )
            task_id = resp.text.strip().strip('"')  # 返回纯字符串

            # Step 2: 轮询结果
            query_url = self.QUERY_URL_TEMPLATE.format(operation_id=task_id)
            while time.time() - start < self.POLL_TIMEOUT:
                await asyncio.sleep(self.POLL_INTERVAL)
                resp = await client.get(query_url, headers=self.headers, timeout=30)
                if resp.status_code != 200:
                    continue
                result = resp.json()
                status = result.get("status")
                if status == 0:  # 生成中
                    continue
                if status == 1:  # 成功
                    parsed = self._parse_gemini_result(result)
                    parsed["duration_ms"] = int((time.time() - start) * 1000)
                    parsed["cached"] = False
                    return parsed
                if status == -1:  # 失败
                    raise RuntimeError(f"Gemini generation failed: {result.get('data')}")
            raise TimeoutError(f"Gemini poll timeout after {self.POLL_TIMEOUT}s")

    def _parse_gemini_result(self, result: dict) -> dict:
        """解析 Gemini 响应：candidates[].content.parts[].{text,inlineData.data}"""
        image_urls = []
        description = ""
        for c in result.get("data", {}).get("candidates", []):
            for p in c.get("content", {}).get("parts", []):
                if p.get("text"):
                    description = p["text"][:200]
                if p.get("inlineData", {}).get("data"):
                    image_urls.append(p["inlineData"]["data"])
        return {"image_urls": image_urls, "description": description}

    # ===== LLMProvider Protocol 实现（Gemini 只支持 image，其他抛 NotImplementedError）=====

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError(
            "Gemini only supports image generation, use generate_image() instead"
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        raise NotImplementedError(
            "Gemini only supports image generation, use generate_image() instead"
        )
        # 保持 async generator 语法合法
        if False:
            yield LLMStreamChunk(provider=ModelProvider.GEMINI)

    def is_available(self) -> bool:
        return True
