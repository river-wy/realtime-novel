"""Gemini Provider（friday 代理 Google 原生异步 submit + poll）

对应 infra.md §B.2.6
"""
from __future__ import annotations

import asyncio
import httpx
import time
from typing import AsyncIterator

from backend.adapters.providers.base import LLMProvider
from backend.adapters.types import (
    LLMRequest, LLMResponse, LLMStreamChunk, ModelProvider,
)
from backend.config.config_loader import load_llm_api_key, get_model_config
from backend.utils.logger import logger


@logger
class GeminiProvider(LLMProvider):
    """friday/gemini-3.1-flash-image-preview（经 friday 代理 Google 原生异步协议）"""

    provider_name = "friday/gemini-3.1-flash-image-preview"
    supported_roles = ["image"]

    def __init__(self, api_key: str | None = None):
        # api_key 走 .llm_api_key 文件，submit_url/query_url_template 从 agents.json 读
        self.api_key = api_key or load_llm_api_key()
        model_cfg = get_model_config("friday/gemini-3.1-flash-image-preview")
        self.SUBMIT_URL = model_cfg["submit_url"]
        self.QUERY_URL_TEMPLATE = model_cfg["query_url_template"]
        # default_params 含轮询配置
        default_params = model_cfg.get("default_params", {})
        self.POLL_INTERVAL = default_params.get("poll_interval", 3)
        self.POLL_TIMEOUT = default_params.get("poll_timeout", 120)
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
        self.log.info("Gemini image START: aspect=%s, size=%s, ref=%s, prompt_len=%d",
                 aspect_ratio, image_size, bool(reference_image_url), len(prompt))
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
            self.log.info("Gemini image SUBMITTED: task_id=%s", task_id)

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
                    duration_ms = int((time.time() - start) * 1000)
                    parsed["duration_ms"] = duration_ms
                    parsed["cached"] = False
                    img_count = len(parsed.get("image_urls", []))
                    self.log.info("Gemini image DONE: task_id=%s, duration_ms=%d, images=%d, desc_len=%d",
                             task_id, duration_ms, img_count, len(parsed.get("description", "")))
                    return parsed
                if status == -1:  # 失败
                    self.log.error("Gemini image FAILED: task_id=%s, data=%s", task_id, result.get("data"))
                    raise RuntimeError(f"Gemini generation failed: {result.get('data')}")
            self.log.error("Gemini image TIMEOUT: task_id=%s, elapsed=%.1fs", task_id, time.time() - start)
            raise TimeoutError(f"Gemini poll timeout after {self.POLL_TIMEOUT}s")

    def _parse_gemini_result(self, result: dict) -> dict:
        """解析 Gemini 响应：candidates[].content.parts[].{text,inlineData.data,fileData}"""
        image_urls = []
        description = ""
        data_obj = result.get("data", {})
        for c in data_obj.get("candidates", []):
            for p in c.get("content", {}).get("parts", []):
                if p.get("text"):
                    description = p["text"][:200]
                # inlineData.data: base64 raw bytes
                inline = p.get("inlineData", {})
                if inline.get("data"):
                    raw = inline["data"]
                    mime = inline.get("mimeType", "")
                    self.log.debug("Gemini part inlineData: mime=%s, data_prefix=%s", mime, str(raw))
                    image_urls.append(raw)
                # fileData.fileUri: 直接是 URL（新版 API 可能返这个）
                file_data = p.get("fileData", {})
                if file_data.get("fileUri"):
                    self.log.debug("Gemini part fileData: uri=%s", file_data["fileUri"])
                    image_urls.append(file_data["fileUri"])
        # 兜底：有些版本直接在 data 层面返 imageUrl 字段
        if not image_urls and data_obj.get("imageUrl"):
            image_urls.append(data_obj["imageUrl"])
        self.log.info("Gemini parse: image_count=%d, description_len=%d", len(image_urls), len(description))
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
