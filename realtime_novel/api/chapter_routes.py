"""Chapter 路由（3 个：list/read/generate）

对应 api.md §B.2
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from pathlib import Path

from realtime_novel.agent.tools import get_tool
from realtime_novel.agent.tools.schemas import (
    ReadChapterInput, GenerateChapterInput,
)
from realtime_novel.persistence import ChapterStatusRepository, ChapterState  # noqa: F401

router = APIRouter(prefix="/api/projects", tags=["chapters"])


class ChapterInfo(BaseModel):
    num: int
    title: str
    summary: Optional[str] = None
    status: str
    time: Optional[str] = None


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


@router.get("/{project_id}/chapters", response_model=ChapterListResponse)
async def list_chapters(project_id: str):
    """列章节"""
    chapters_dir = Path(f"data/{project_id}/chapters")
    chapters = []
    if chapters_dir.exists():
        for f in sorted(chapters_dir.glob("chapter_*.md")):
            num = int(f.stem.split("_")[1])
            chapters.append(ChapterInfo(
                num=num,
                title=f"第 {num} 章",
                status="done",
                time=datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            ))
    return ChapterListResponse(chapters=chapters)


@router.get("/{project_id}/chapters/{n}", response_model=ChapterContentResponse)
async def read_chapter(
    project_id: str,
    n: int = Path(ge=1),
):
    """读章节正文"""
    chapter_path = Path(f"data/{project_id}/chapters/chapter_{n:03d}.md")
    if not chapter_path.exists():
        raise HTTPException(404, f"Chapter {n} not found")
    content = chapter_path.read_text()
    title = ""
    for line in content.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return ChapterContentResponse(
        num=n,
        title=title or f"第 {n} 章",
        content=content,
        word_count=len(content),
        generated_at=datetime.fromtimestamp(chapter_path.stat().st_mtime).isoformat(),
    )


@router.post("/{project_id}/chapters", response_model=GenerateChapterResponse)
async def generate_chapter(
    project_id: str,
    req: GenerateChapterRequest,
):
    """生成下一章（60-100s 端到端）— 薄路由，只调 tool"""
    tool = get_tool("generate_chapter")
    input_obj = GenerateChapterInput(
        project_id=project_id,
        intervention=req.intervention,
        actor_feedback=req.actor_feedback,
        actor_character=req.actor_character,
    )
    from realtime_novel.agent.tools.base import ToolError
    output = await tool.run(input_obj)
    if isinstance(output, ToolError):
        if output.code == "CONCURRENT_GENERATION":
            raise HTTPException(409, output.message)
        raise HTTPException(500, f"Chapter generation failed: {output.message}")
    return GenerateChapterResponse(
        chapter_num=output.num,
        title=output.title,
        content=output.content,
        word_count=output.word_count,
        generated_at=output.generated_at or datetime.now().isoformat(),
        new_seeds_triggered=0,
    )
