"""onboarding_hooks — Onboarding 领域事件 handler 注册

本模块被 import 时自动向 event_bus 注册所有 onboarding 相关的后置钩子。
只需在 app startup 里 import 一次，无需显式调用任何函数。

当前注册的事件：
  onboarding.step4_confirmed
    → 并发生成项目名称 + 封面图，结果落库并尝试推 WS 事件
"""
from __future__ import annotations

import asyncio

from backend.core.event_bus import event_bus
from backend.adapters.types import LLMRequest, ModelRole
from backend.utils.logger import logger as logger_decorator


# ============ 项目名自动生成 ============

GENERATE_NAME_PROMPT = """你是「小说命名师」。根据下面的故事核心, 生成 1 个项目名。

要求:
- 中文 (1-15 字, 鼓励), 也可英文
- 携带故事核心悬念/冲突的关键词
- 避免「小说/世界/世界线」等泛词
- 不用冒号/书名号
- 1 个, 不要列表

示例 (看格式不抄内容):
- 白小楼借仙界一季还雪国万灯
- 杀妻者自赎录
- The Last Letter from Mars

故事核心: {story_core}
主角/对手/盟友: {characters}
题材: {tone}

只返名字, 不要说明, 不要引号. 严格返一个 string.
"""


@logger_decorator
async def _generate_project_name(story_core: str, characters: str, tone: list[str] | str) -> str:
    """Step 4 完成后 LLM 自动生成项目名"""
    from backend.adapters import get_llm_adapter

    if isinstance(tone, str):
        tone = [tone] if tone else []
    tone_str = ", ".join(tone) or "(未选)"

    try:
        adapter = get_llm_adapter()
        request = LLMRequest(
            prompt="",
            messages=[{
                "role": "user",
                "content": GENERATE_NAME_PROMPT.format(
                    story_core=story_core[:300],
                    characters=characters[:300],
                    tone=tone_str,
                ),
            }],
            max_tokens=200,
            temperature=0.7,
            role=ModelRole.TEXT,
            enable_thinking=False,
        )
        response = await adapter.complete(request)
        raw = (response.content or "").strip()
        name = raw.split("\n")[0].strip().strip("'\"`'「」《》")
        name = name[:50]
        if not name or len(name) < 2:
            _generate_project_name.log.warning("auto-name: too short, raw=%s", raw[:100])
            return ""
        _generate_project_name.log.info("auto-name generated: %s", name)
        return name
    except Exception as e:
        _generate_project_name.log.error("auto-name failed: %s", str(e))
        return ""


# ============ Event Handlers ============

@event_bus.on("onboarding.step4_confirmed")
@logger_decorator
async def handle_step4_confirmed(
    project_id: str,
    payload: dict,
    ws=None,      # WebSocket 实例，可选（WS 已断开时为 None 或推送失败都安全）
    **kwargs,
) -> None:
    """Step 4 确认后置钩子：并发生成项目名称 + 封面图

    与 WS 连接状态完全解耦：
    - 落库操作（update_name / update_cover_image_url）无论 WS 是否在线都会执行
    - WS 推送在 try/except 里，失败静默忽略
    """
    from backend.persistence.project_repository import ProjectRepository
    from backend.services.onboarding_flow import OnboardingFlow
    from backend.services.cover_image_generator import generate_and_save_cover
    from backend.config.config_loader import PROJECT_ROOT
    from pathlib import Path

    projects_root: Path = PROJECT_ROOT / "data" / "projects"
    proj_repo = ProjectRepository()

    handle_step4_confirmed.log.info("onboarding_hooks: step4_confirmed START project_id=%s", project_id)

    name_task = _generate_project_name(
        story_core=payload.get("story_core", ""),
        characters=payload.get("characters", ""),
        tone=payload.get("tone", []),
    )
    cover_task = generate_and_save_cover(
        project_id=project_id,
        payload=payload,
        projects_root=projects_root,
    )

    new_name, cover_image_url = await asyncio.gather(
        name_task, cover_task, return_exceptions=True
    )

    # ── 处理名称 ──────────────────────────────────────────
    if isinstance(new_name, Exception):
        handle_step4_confirmed.log.warning("onboarding_hooks: name generation failed: %s", new_name)
        new_name = None
    if new_name:
        proj_repo.update_name(project_id, new_name)
        OnboardingFlow().update_project_name_in_state(project_id, new_name)
        handle_step4_confirmed.log.info("onboarding_hooks: name saved project_id=%s name=%r", project_id, new_name)
        if ws is not None:
            try:
                await ws.send_json({
                    "type": "project_name_updated",
                    "project_id": project_id,
                    "name": new_name,
                })
            except Exception:
                pass  # WS 已断开，忽略

    # ── 处理封面图 ────────────────────────────────────────
    if isinstance(cover_image_url, Exception):
        handle_step4_confirmed.log.warning("onboarding_hooks: cover generation failed: %s", cover_image_url)
        cover_image_url = None
    if cover_image_url:
        proj_repo.update_cover_image_url(project_id, cover_image_url)
        handle_step4_confirmed.log.info("onboarding_hooks: cover saved project_id=%s url=%s", project_id, cover_image_url)
        if ws is not None:
            try:
                await ws.send_json({
                    "type": "cover_image_updated",
                    "project_id": project_id,
                    "cover_image_url": cover_image_url,
                })
            except Exception:
                pass  # WS 已断开，忽略

    handle_step4_confirmed.log.info("onboarding_hooks: step4_confirmed DONE project_id=%s name=%r cover=%s",
             project_id, new_name, cover_image_url)
