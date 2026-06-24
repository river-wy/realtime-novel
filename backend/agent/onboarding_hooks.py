"""onboarding_hooks — Onboarding 领域事件 handler 注册

本模块被 import 时自动向 event_bus 注册所有 onboarding 相关的后置钩子。
只需在 app startup 里 import 一次，无需显式调用任何函数。

当前注册的事件：
  onboarding.step4_confirmed
    → 并发生成项目名称 + 封面图，结果落库并尝试推 WS 事件
"""
from __future__ import annotations

import asyncio
import logging

from backend.core.event_bus import event_bus

log = logging.getLogger(__name__)


@event_bus.on("onboarding.step4_confirmed")
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
    from backend.agent.onboarding_agent import _generate_project_name
    from backend.persistence.project_repository import ProjectRepository
    from backend.services.onboarding_flow import OnboardingFlow
    from backend.services.cover_image_generator import generate_and_save_cover
    from backend.config.config_loader import PROJECT_ROOT
    from pathlib import Path

    projects_root: Path = PROJECT_ROOT / "data" / "projects"
    proj_repo = ProjectRepository()

    log.info("onboarding_hooks: step4_confirmed START project_id=%s", project_id)

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
        log.warning("onboarding_hooks: name generation failed: %s", new_name)
        new_name = None
    if new_name:
        proj_repo.update_name(project_id, new_name)
        OnboardingFlow().update_project_name_in_state(project_id, new_name)
        log.info("onboarding_hooks: name saved project_id=%s name=%r", project_id, new_name)
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
        log.warning("onboarding_hooks: cover generation failed: %s", cover_image_url)
        cover_image_url = None
    if cover_image_url:
        proj_repo.update_cover_image_url(project_id, cover_image_url)
        log.info("onboarding_hooks: cover saved project_id=%s url=%s", project_id, cover_image_url)
        if ws is not None:
            try:
                await ws.send_json({
                    "type": "cover_image_updated",
                    "project_id": project_id,
                    "cover_image_url": cover_image_url,
                })
            except Exception:
                pass  # WS 已断开，忽略

    log.info("onboarding_hooks: step4_confirmed DONE project_id=%s name=%r cover=%s",
             project_id, new_name, cover_image_url)

