"""Chapter 路由（3 个：list/read/generate）

对应 api.md §B.2
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path as FsPath
from typing import Optional

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from backend.agent.tools import get_tool
from backend.agent.tools.schemas import (
    GenerateChapterInput,
)
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
    actor_feedback: Optional[str] = None
    actor_character: Optional[str] = None


class GenerateChapterResponse(BaseModel):
    chapter_num: int
    title: str
    content: str
    word_count: int
    generated_at: str
    new_seeds_triggered: int = 0
    summary: Optional[str] = None  # v0.5 新增：1 句话 summary


@router.get("/{project_id}/chapters", response_model=ChapterListResponse)
async def list_chapters(project_id: str):
    """列章节（v0.5 走 DB，v0.4 走文件）"""
    from backend.persistence import ChapterRepository
    chap_repo = ChapterRepository()
    rows = chap_repo.list_by_project(project_id, limit=200)
    chapters = []
    for r in rows:
        chapters.append(ChapterInfo(
            num=r.chapter_num,
            title=r.title or f"第 {r.chapter_num} 章",
            summary=r.summary,  # v0.5 新增
            status="done",
            time=r.generated_at.isoformat() if r.generated_at else None,
        ))
    return ChapterListResponse(chapters=chapters)


@router.get("/{project_id}/chapters/{n}", response_model=ChapterContentResponse)
async def read_chapter(
    project_id: str,
    n: int = Path(ge=1),
):
    """读章节正文（v0.5 走 DB，正文从 file_path 读）"""
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
    """生成下一章（60-100s 端到端）— 薄路由，只调 tool（v0.4.1 落库）"""
    tool = get_tool("generate_chapter")
    input_obj = GenerateChapterInput(
        project_id=project_id,
        intervention=req.intervention,
        actor_feedback=req.actor_feedback,
        actor_character=req.actor_character,
    )
    from backend.agent.tools.base import ToolError
    output = await tool.run(input_obj)
    if isinstance(output, ToolError):
        if output.code == "CONCURRENT_GENERATION":
            raise HTTPException(409, output.message)
        raise HTTPException(500, f"Chapter generation failed: {output.message}")
    # v0.4.1 落库 (via ConversationRepository)
    result_dict = output.model_dump() if hasattr(output, "model_dump") else {"_raw": str(output)}
    conv_repo = ConversationRepository()
    conv = await conv_repo.get_or_create_active_conversation("default")
    await conv_repo.add_message(
        conversation_id=conv.id,
        role=MessageRole.TOOL,
        tool_results={"name": "generate_chapter",
                      "args": {"project_id": project_id, "intervention": req.intervention,
                               "actor_feedback": req.actor_feedback, "actor_character": req.actor_character},
                      "result": result_dict},
        project_id=project_id,
    )
    return GenerateChapterResponse(
        chapter_num=output.num,
        title=output.title,
        content=output.content,
        word_count=output.word_count,
        generated_at=output.generated_at or datetime.now().isoformat(),
        new_seeds_triggered=0,
        summary=getattr(output, "summary", None),
    )
