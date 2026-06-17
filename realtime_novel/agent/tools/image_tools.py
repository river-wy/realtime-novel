"""Image 工具（generate_image，cache by prompt hash）

对应 core.md §B.1
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from realtime_novel.agent.tools.base import BaseTool, ToolError, register_tool
from realtime_novel.agent.tools.schemas import GenerateImageInput, ImageResult
from realtime_novel.adapters import get_llm_adapter


# 简单内存 cache（v0.4 阶段，生产可换 Redis）
_image_cache: dict[str, ImageResult] = {}


class GenerateImageTool(BaseTool):
    name = "generate_image"
    description = "生成主立绘（调 Gemini 文生图，按 prompt hash 缓存）"
    input_schema = GenerateImageInput
    output_schema = ImageResult

    def __init__(self):
        self._adapter = get_llm_adapter()

    def _cache_key(self, project_id: str, prompt: str, style_hint: str | None) -> str:
        raw = f"{project_id}|{prompt}|{style_hint or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def run(self, input: GenerateImageInput, progress_callback=None) -> ImageResult:
        cache_key = self._cache_key(input.project_id, "main_cover", input.style_hint)
        # 查 cache
        if cache_key in _image_cache:
            cached = _image_cache[cache_key]
            if progress_callback:
                await progress_callback({"step": "cache_hit", "percentage": 100})
            return ImageResult(
                project_id=input.project_id,
                image_url=cached.image_url,
                generated_at=cached.generated_at,
                cache_hit=True,
            )
        # 调 Gemini
        try:
            if progress_callback:
                await progress_callback({"step": "submitting", "percentage": 20})
            result = await self._adapter.generate_image(
                prompt=f"为小说项目 {input.project_id} 生成主立绘",
                aspect_ratio="1:1",
                image_size="1K",
            )
            if progress_callback:
                await progress_callback({"step": "polling", "percentage": 60})
            image_urls = result.get("image_urls", [])
            if not image_urls:
                return ToolError(code="EMPTY_RESULT", message="Gemini returned no images")
            # 取第一个
            image_url = image_urls[0]
            # 写 cache
            image_result = ImageResult(
                project_id=input.project_id,
                image_url=image_url,
                generated_at=datetime.now().isoformat(),
                cache_hit=False,
            )
            _image_cache[cache_key] = image_result
            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return image_result
        except TimeoutError as e:
            return ToolError(code="POLL_TIMEOUT", message=str(e))
        except Exception as e:
            return ToolError(code="GENERATION_FAILED", message=str(e))


register_tool(GenerateImageTool())
