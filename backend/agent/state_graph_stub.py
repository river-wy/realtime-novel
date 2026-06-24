"""State graph stub

完整流程：
1. 调 LLM 生成章节正文（一次性，含 summary sentinel 块）
2. 解析 sentinel 抽 summary
3. sentinel 解析失败 → 调 LLM 单独生成 2 句话概括（不截正文）
4. 章节 metadata + summary 入 DB，正文留文件
5. 触发 chapter_seed_changes / chapter_character_states 记录

"""
from __future__ import annotations

import logging
from typing import Optional

from backend.agent.chapter_summarizer import (
    fallback_summary,
)

logger = logging.getLogger(__name__)


async def _generate_summary_via_llm(chapter_content: str, project_id: str) -> Optional[str]:
    """当 sentinel 解析失败时，调 LLM 单独生成 2 句话概括

    Args:
        chapter_content: 纯正文（已剥离 sentinel 块）
        project_id: 项目 ID（用于日志）

    Returns:
        2 句话 summary，失败返回 None
    """
    try:
        from backend.adapters.llm_adapter import get_llm_adapter
        from backend.adapters.types import ModelRole

        adapter = get_llm_adapter()
        # 限制正文长度避免超 token（取前 3000 字足够概括）
        content_snippet = chapter_content[:3000]

        prompt = f"""请用两句话概括以下小说章节的核心故事发展（不是描述开头，而是概括整章的情节推进和关键事件）：

{content_snippet}

要求：
- 恰好两句话
- 概括整章最重要的情节推进，不是复述开头
- 简洁，~50-100 字
- 直接输出两句话，不要加任何前缀或解释"""

        response = await adapter.complete_with_messages(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="你是一个专业的小说内容编辑，擅长用简洁语言概括章节核心情节。",
            max_tokens=400,
            temperature=0.3,
            role=ModelRole.TEXT,
            enable_thinking=False,  # summary 生成不需要 thinking，关闭节省 token
        )
        summary = response.content.strip()
        if summary:
            logger.info(f"[{project_id}] sentinel 解析失败，LLM 补生成 summary 成功")
            return summary
    except Exception as e:
        logger.warning(f"[{project_id}] LLM fallback summary 生成失败: {e}")
    return None


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

    # 2. fallback：sentinel 解析失败 → 调 LLM 单独生成 2 句话概括 → 最后才截正文
    if not chapter_summary and chapter_content:
        chapter_summary = await _generate_summary_via_llm(chapter_content, project_id)
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

    # 3.5 从正文首行 "# ..." 提取章节标题，fallback 到"第N章"
    chapter_title = f"第 {next_num} 章"
    for line in chapter_content.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            chapter_title = line[2:].strip()
            break

    # 4. 入 DB
    chap_repo.create(
        project_id=project_id,
        chapter_num=next_num,
        file_path=str(chapter_path),
        title=chapter_title,
        content_text=None,
        word_count=len(chapter_content),
        intervention=intervention,
        actor_feedback=actor_feedback,
        actor_character=actor_character,
        summary=chapter_summary,
    )

    return {
        "num": next_num,
        "title": chapter_title,
        "content": chapter_content,
        "file_path": str(chapter_path),
        "word_count": len(chapter_content),
        "summary": chapter_summary,
    }
