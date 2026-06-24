"""cover_image_generator — 世界封面图生成服务

v0.9: onboarding Step 4 完成后，并发调 Gemini 生图
- 根据 story_core/characters/genres/tone 生成图片 prompt
- 调 GeminiProvider.generate_image（1:1 比例）
- base64 → 保存为 PNG 文件到 data/projects/{id}/cover.png
- 写 projects.cover_image_url = /static/projects/{id}/cover.png
- 推 WS 事件 cover_image_updated 给前端
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from backend.utils.logger import logger

# 封面图 prompt 模板
COVER_IMAGE_PROMPT_TEMPLATE = """Generate a stunning 1:1 square book cover illustration for a novel with the following story:

Story core: {story_core}
Main characters: {characters}
Genres: {genres}
Tone: {tone}

Art style requirements:
- Epic, cinematic, high-quality digital art
- Rich atmospheric lighting and dramatic composition
- Chinese novel aesthetic, suitable for light novel / webnovel cover
- No text, no title, no watermark
- Single focused scene that captures the essence of the story
- Vibrant colors with strong visual hierarchy"""


def build_cover_prompt(payload: dict) -> str:
    """从 onboarding payload 构建封面图 prompt"""
    story_core = payload.get("story_core", "")[:200]
    characters = payload.get("characters", "")[:200]
    genres = ", ".join(payload.get("genres", [])) or payload.get("tone", "")
    if isinstance(genres, list):
        genres = ", ".join(genres)
    tone_list = payload.get("tone", [])
    if isinstance(tone_list, list):
        tone = ", ".join(tone_list)
    else:
        tone = str(tone_list)

    return COVER_IMAGE_PROMPT_TEMPLATE.format(
        story_core=story_core or "An epic adventure story",
        characters=characters or "A brave hero",
        genres=genres or "Fantasy",
        tone=tone or "Epic",
    )


@logger
async def generate_and_save_cover(
    project_id: str,
    payload: dict,
    projects_root: Path,
) -> Optional[str]:
    """生成封面图并保存到本地，返回 URL 路径（失败返回 None）

    Args:
        project_id: 项目 ID
        payload: onboarding state_json.payload（含 story_core/characters/genres/tone）
        projects_root: data/projects/ 目录路径

    Returns:
        静态 URL 路径，如 /static/projects/world-3f7a8b2c/cover.png
        失败时返回 None
    """
    try:
        from backend.adapters.llm_adapter import get_llm_adapter

        prompt = build_cover_prompt(payload)
        generate_and_save_cover.log.info("[%s] 开始生成封面图，prompt 长度=%d", project_id, len(prompt))

        adapter = get_llm_adapter()
        result = await adapter.generate_image(
            prompt=prompt,
            aspect_ratio="1:1",
            image_size="1K",
        )

        image_urls = result.get("image_urls", [])
        if not image_urls:
            generate_and_save_cover.log.warning("[%s] Gemini 未返回图片数据", project_id)
            return None

        # Gemini 返回的是 base64 data 或直接 URL
        image_data = image_urls[0]
        if not image_data:
            generate_and_save_cover.log.warning("[%s] 图片数据为空", project_id)
            return None

        generate_and_save_cover.log.info("[%s] 图片数据前缀: %s", project_id, str(image_data)[:80])

        project_dir = projects_root / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        cover_path = project_dir / "cover.png"

        # 判断是 URL 还是 base64
        if image_data.startswith("http://") or image_data.startswith("https://"):
            # 直接是 URL → 下载
            import httpx
            generate_and_save_cover.log.info("[%s] 图片是 URL，开始下载: %s", project_id, image_data[:100])
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(image_data)
                resp.raise_for_status()
                image_bytes = resp.content
        else:
            # base64 数据（可能带 data:image/xxx;base64, 前缀）
            if "," in image_data and image_data.startswith("data:"):
                image_data = image_data.split(",", 1)[1]
            # 修复 padding（base64 要求长度是 4 的倍数）
            image_data = image_data.strip()
            padding = 4 - len(image_data) % 4
            if padding != 4:
                image_data += "=" * padding
            try:
                image_bytes = base64.b64decode(image_data)
            except Exception as e:
                generate_and_save_cover.log.error("[%s] base64 解码失败: %s, data_prefix=%s",
                                                  project_id, str(e), str(image_data)[:60])
                return None

        cover_path.write_bytes(image_bytes)
        generate_and_save_cover.log.info("[%s] 封面图已保存到 %s，大小=%d bytes", project_id, cover_path, len(image_bytes))

        # 返回静态 URL 路径
        static_url = f"/static/projects/{project_id}/cover.png"
        return static_url

    except Exception as e:
        generate_and_save_cover.log.error("[%s] 封面图生成失败: %s", project_id, str(e), exc_info=True)
        return None

