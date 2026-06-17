"""State graph 临时 stub（chapter_tools 用）

Phase 2 临时版：返回 placeholder 章节，不调真实 LangGraph。
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
    """占位：返回 3500 字 placeholder 章节 + 写入文件（Phase 3 替换为真实 LangGraph）"""
    # 模拟 60-100s 延迟（v0.4 实际是真实 LLM 60-100s；这里立即返回）
    import asyncio
    import os
    from pathlib import Path
    await asyncio.sleep(0.01)
    # 算 next chapter num
    from realtime_novel.services.async_wrappers import AsyncProjectManager
    pm = AsyncProjectManager()
    project = await pm.load(project_id)
    if project is None:
        raise FileNotFoundError(f"Project not found: {project_id}")
    chapters = project.get("chapters", [])
    next_num = len(chapters) + 1
    body = (
        f"# 第 {next_num} 章\n\n"
        f"（占位章节 — Phase 3 接入 LangGraph state-graph 后替换）\n\n"
        f"项目：{project_id}\n"
        f"干预：{intervention or '无'}\n"
        f"演员反馈：{actor_feedback or '无'}\n"
        f"演员角色：{actor_character or '无'}\n\n"
        f"本章内容由 v0.4 状态机自动生成。\n" * 50
    )
    # 写文件
    chapters_dir = Path(f"data/projects/{project_id}/chapters")
    chapters_dir.mkdir(parents=True, exist_ok=True)
    chapter_path = chapters_dir / f"chapter_{next_num:03d}.md"
    chapter_path.write_text(body)
    return {
        "num": next_num,
        "title": f"第 {next_num} 章",
        "content": body,
    }
