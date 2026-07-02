"""Chapter 路由（3 个：list/read/generate）

对应 api.md §B.2
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path as FsPath
from typing import Optional

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from backend.persistence import ConversationRepository, \
    MessageRole  # noqa: F401

router = APIRouter(prefix="/api/projects", tags=["chapters"])


class ChapterInfo(BaseModel):
    num: int
    title: str
    summary: Optional[str] = None
    status: str
    time: Optional[str] = None
    word_count: Optional[int] = None
    file_path: Optional[str] = None


class ChapterListResponse(BaseModel):
    chapters: list[ChapterInfo]


class ChapterContentResponse(BaseModel):
    num: int
    title: str
    content: str
    word_count: int
    generated_at: Optional[str] = None


class GenerateChapterRequest(BaseModel):
    intervention: Optional[str] = None


class GenerateChapterResponse(BaseModel):
    chapter_num: int
    title: str
    content: str
    word_count: int
    generated_at: str
    new_seeds_triggered: int = 0
    summary: Optional[str] = None  # 1 句话 summary


@router.get("/{project_id}/chapters", response_model=ChapterListResponse)
async def list_chapters(project_id: str):
    """列章节"""
    from backend.persistence import ChapterRepository
    chap_repo = ChapterRepository()
    rows = chap_repo.list_by_project(project_id, limit=200)
    chapters = []
    for r in rows:
        chapters.append(ChapterInfo(
            num=r.chapter_num,
            title=r.title or f"第 {r.chapter_num} 章",
            summary=r.summary,
            status="done",
            time=r.generated_at.isoformat() if r.generated_at else None,
        ))
    return ChapterListResponse(chapters=chapters)


@router.get("/{project_id}/chapters/{n}", response_model=ChapterContentResponse)
async def read_chapter(
    project_id: str,
    n: int = Path(ge=1),
):
    """读章节正文（走 DB，正文从 file_path 读）"""
    from backend.persistence import ChapterRepository
    from backend.config.config_loader import PROJECT_ROOT
    chap_repo = ChapterRepository()
    row = chap_repo.get(project_id, n)
    if not row:
        raise HTTPException(404, f"Chapter {n} not found")
    # 正文从 file_path 读 (相对路径基于 PROJECT_ROOT)
    chapter_path = FsPath(row.file_path)
    if not chapter_path.is_absolute():
        chapter_path = PROJECT_ROOT / chapter_path
    if not chapter_path.exists():
        raise HTTPException(404, f"Chapter file not found: {row.file_path}")
    content = chapter_path.read_text()
    # 优先用 DB 里的标题；若 DB 标题只是"第N章"占位符，则从正文首行 # 提取
    title = row.title or ""
    import re as _re
    if not title or _re.fullmatch(r"第\s*\d+\s*章", title):
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                extracted = line[2:].strip()
                if extracted and not _re.fullmatch(r"第\s*\d+\s*章", extracted):
                    title = extracted
                    # 回填 DB，修复旧章节的占位符 title
                    from backend.persistence import get_store
                    with get_store().connection() as conn:
                        conn.execute(
                            "UPDATE chapters SET title = ? WHERE project_id = ? AND chapter_num = ?",
                            (title, project_id, n),
                        )
                break
    if not title:
        title = f"第 {n} 章"
    return ChapterContentResponse(
        num=n,
        title=title,
        content=content,
        word_count=len(content),
        generated_at=row.generated_at.isoformat() if row.generated_at else None,
    )


@router.post("/{project_id}/chapters", response_model=GenerateChapterResponse)
async def generate_chapter(
    project_id: str,
    req: GenerateChapterRequest,
):
    """生成下一章（60-100s 端到端）— 薄路由，委托给文笔家 Agent

    内部调 delegate_chapter_generation()，走文笔家 ReAct loop，
    最终调 generate_chapter / summarize_chapter 工具落盘。
    """
    from backend.agent.agents.novel_writer import delegate_chapter_generation

    chapter_output = await delegate_chapter_generation(
        project_id=project_id,
        intervention=req.intervention,
        source="page_button",
    )

    if chapter_output.error:
        # 文笔家 ReAct loop 返回错误（保留 409 并发语义）
        if "CONCURRENT_GENERATION" in chapter_output.error:
            raise HTTPException(409, chapter_output.error)
        raise HTTPException(500, f"Chapter generation failed: {chapter_output.error}")

    # 落 conversation (via ConversationRepository)
    conv_repo = ConversationRepository()
    conv = await conv_repo.get_or_create_active_conversation("default")
    await conv_repo.add_message(
        conversation_id=conv.id,
        role=MessageRole.TOOL,
        tool_results={
            "name": "delegate_chapter_generation",
            "args": {
                "project_id": project_id,
                "intervention": req.intervention,
                "source": "page_button",
            },
            "result": {
                "chapter_num": chapter_output.chapter_num,
                "title": chapter_output.title,
                "word_count": chapter_output.word_count,
                "summary": chapter_output.chapter_summary,
            },
        },
        project_id=project_id,
        agent_name="novel_writer",
    )

    return GenerateChapterResponse(
        chapter_num=chapter_output.chapter_num or 0,
        title=chapter_output.title or "",
        content=chapter_output.chapter_content,
        word_count=chapter_output.word_count or len(chapter_output.chapter_content),
        generated_at=datetime.now().isoformat(),
        new_seeds_triggered=0,
        summary=chapter_output.chapter_summary,
    )
