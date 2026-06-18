"""State graph 临时 stub（chapter_tools 用）

Phase 2 临时版：返回 placeholder 章节。
v0.4.1: 章节 metadata 入 DB，正文留文件
Phase 3 写 novel-agent-state-graph 时替换为真实 build_graph() 调用。
"""
from __future__ import annotations

import asyncio
from typing import Optional


async def generate_chapter_via_state_graph(
    project_id: str,
    intervention: Optional[str] = None,
    actor_feedback: Optional[str] = None,
    actor_character: Optional[str] = None,
) -> dict:
    """占位：返回 placeholder 章节（v0.4.1 metadata 入 DB + 正文写文件）

    Phase 3 替换为真实 LangGraph（带 LLM 调用 + summary 同步生成）
    """
    from pathlib import Path
    from datetime import datetime
    from realtime_novel.services.async_wrappers import AsyncProjectManager
    from realtime_novel.persistence import ChapterRepository

    pm = AsyncProjectManager()
    project = await pm.load(project_id)
    if project is None:
        raise FileNotFoundError(f"Project not found: {project_id}")

    # 算 next chapter num
    chap_repo = ChapterRepository()
    existing_count = chap_repo.count_chapters(project_id)
    next_num = existing_count + 1

    body = (
        f"# 第 {next_num} 章\n\n"
        f"（占位章节 — Phase 3 接入 LangGraph state-graph 后替换）\n\n"
        f"项目：{project_id}\n"
        f"干预：{intervention or '无'}\n"
        f"演员反馈：{actor_feedback or '无'}\n"
        f"演员角色：{actor_character or '无'}\n\n"
        f"本章内容由 v0.4.1 状态机自动生成。\n" * 50
    )

    # 写文件
    chapters_dir = Path(f"data/projects/{project_id}/chapters")
    chapters_dir.mkdir(parents=True, exist_ok=True)
    chapter_path = chapters_dir / f"chapter_{next_num:03d}.md"
    chapter_path.write_text(body, encoding="utf-8")

    # 入 DB（metadata）
    chap_repo.create(
        project_id=project_id,
        chapter_num=next_num,
        file_path=str(chapter_path),
        title=f"第 {next_num} 章",
        content_text=None,  # 已写文件，不重复传
        word_count=len(body),
        intervention=intervention,
        actor_feedback=actor_feedback,
        actor_character=actor_character,
    )

    return {
        "num": next_num,
        "title": f"第 {next_num} 章",
        "content": body,
        "file_path": str(chapter_path),
        "word_count": len(body),
    }
