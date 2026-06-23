"""State graph stub（chapter_tools 用）v0.5 真实 LLM 版

v0.5 完整流程：
1. 调 LLM 生成章节正文（一次性，含 summary sentinel 块）
2. 解析 sentinel 抽 summary
3. 章节 metadata + summary 入 DB，正文留文件
4. 触发 chapter_seed_changes / chapter_character_states 记录（v0.5 阶段 C）

Phase 3 写 novel-agent-state-graph 时替换为真实 build_graph() 调用
"""
from __future__ import annotations

from typing import Optional

from backend.agent.chapter_summarizer import (
    fallback_summary,
)


async def generate_chapter_via_state_graph(
    project_id: str,
    intervention: Optional[str] = None,
    actor_feedback: Optional[str] = None,
    actor_character: Optional[str] = None,
) -> dict:
    """v0.5 真实 LLM 版章节生成

    流程：
    1. 拿当前章节数 → next_num
    2. 调 LLM（ChapterGeneratorSpecialist）生成章节 + summary
    3. 解析 sentinel 抽 summary
    4. 写文件 + 入 DB
    5. 返回完整结果
    """
    from backend.persistence import ChapterRepository
    from backend.persistence.project_repository import ProjectRepository

    # 直接用 persistence 层，避免 agent → services 的反向依赖
    _proj_repo = ProjectRepository()
    project_row = _proj_repo.get(project_id)
    if project_row is None:
        raise FileNotFoundError(f"Project not found: {project_id}")
    project = {"id": project_row.id, "name": project_row.name}

    chap_repo = ChapterRepository()
    existing_count = chap_repo.count_chapters(project_id)
    next_num = existing_count + 1

    # 1. 调 LLM（用 ChapterGeneratorSpecialist W2 真实实现）
    from backend.agent.specialists import ChapterGeneratorSpecialist
    specialist = ChapterGeneratorSpecialist()

    # 拼 user_message
    user_message_parts = [f"请生成第 {next_num} 章"]
    if intervention:
        user_message_parts.append(f"用户干预: {intervention}")
    if actor_feedback:
        user_message_parts.append(f"演员反馈: {actor_feedback}")
    if actor_character:
        user_message_parts.append(f"演员角色: {actor_character}")
    user_message = "\n".join(user_message_parts)

    result = await specialist.consult({
        "project_id": project_id,
        "user_message": user_message,
        "max_history": 5,
    })

    chapter_content = result.get("chapter_content", "")
    chapter_summary = result.get("chapter_summary")

    # 2. fallback（解析失败）
    if not chapter_summary:
        chapter_summary = fallback_summary(chapter_content, max_chars=100)
    if not chapter_content:
        chapter_content = f"# 第 {next_num} 章\n\n（章节生成失败：{result.get('opinion', '未知错误')}）\n"

    # 3. 写文件
    from backend.config.config_loader import PROJECT_ROOT
    chapters_dir = PROJECT_ROOT / f"data/projects/{project_id}/chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    chapter_path = chapters_dir / f"chapter_{next_num:03d}.md"
    chapter_path.write_text(chapter_content, encoding="utf-8")

    # 4. 入 DB
    chap_repo.create(
        project_id=project_id,
        chapter_num=next_num,
        file_path=str(chapter_path),
        title=f"第 {next_num} 章",
        content_text=None,
        word_count=len(chapter_content),
        intervention=intervention,
        actor_feedback=actor_feedback,
        actor_character=actor_character,
        summary=chapter_summary,
    )

    return {
        "num": next_num,
        "title": f"第 {next_num} 章",
        "content": chapter_content,
        "file_path": str(chapter_path),
        "word_count": len(chapter_content),
        "summary": chapter_summary,
    }
