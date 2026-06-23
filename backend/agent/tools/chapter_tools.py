"""Chapter 工具（generate_chapter / read_chapter）

对应 core.md §B.1
"""
from __future__ import annotations

from typing import Optional, Callable, Awaitable
from datetime import datetime
from pathlib import Path

from backend.agent.tools.base import BaseTool, ToolError, register_tool
from backend.agent.tools.schemas import (
    GenerateChapterInput, ReadChapterInput, ChapterContent,
)
from backend.agent.tools.locks import get_project_lock
from backend.services.async_wrappers import AsyncProjectManager
from backend.persistence import ChapterStatusRepository, ChapterState


class GenerateChapterTool(BaseTool):
    name = "generate_chapter"
    description = "生成下一章（60-100s 端到端；同项目并发返回 409）"
    input_schema = GenerateChapterInput
    output_schema = ChapterContent

    def __init__(self):
        self._pm = AsyncProjectManager()
        self._status_repo = ChapterStatusRepository()

    async def run(
        self, input: GenerateChapterInput, progress_callback=None
    ) -> ChapterContent:
        lock = get_project_lock(input.project_id)
        if lock.locked():
            return ToolError(
                code="CONCURRENT_GENERATION",
                message=f"项目 {input.project_id} 正在生成其他章节",
            )
        async with lock:
            try:
                # 标 generating
                proj = await self._pm.load(input.project_id)
                existing = proj.get("chapters", []) if proj else []
                next_chapter_num = len(existing) + 1

                await self._status_repo.set_status(
                    input.project_id, next_chapter_num, ChapterState.GENERATING
                )
                if progress_callback:
                    await progress_callback({"step": "generating", "percentage": 10})

                # v0.4 简化版：不调真实 v0.3 ChapterGenerator（避免依赖 WorldTree/Project 复杂初始化）
                # 直接生成 placeholder 章节（Phase 4 接入真实 v0.3 时替换）
                from backend.agent.state_graph_stub import generate_chapter_via_state_graph
                chapter = await generate_chapter_via_state_graph(
                    project_id=input.project_id,
                    intervention=input.intervention,
                    actor_feedback=input.actor_feedback,
                    actor_character=input.actor_character,
                )
                if progress_callback:
                    await progress_callback({"step": "done", "percentage": 100})

                # 标 done
                await self._status_repo.set_status(
                    input.project_id, next_chapter_num, ChapterState.DONE
                )
                return ChapterContent(
                    num=next_chapter_num,
                    title=chapter.get("title", f"第 {next_chapter_num} 章"),
                    content=chapter.get("content", ""),
                    word_count=len(chapter.get("content", "")),
                    generated_at=datetime.now().isoformat(),
                    summary=chapter.get("summary"),  # v0.5 新增
                )
            except Exception as e:
                try:
                    await self._status_repo.set_status(
                        input.project_id, next_chapter_num, ChapterState.FAILED, error=str(e)
                    )
                except Exception:
                    pass
                return ToolError(code="GENERATION_FAILED", message=str(e))


class ReadChapterTool(BaseTool):
    name = "read_chapter"
    description = "读章节正文（从 Markdown 文件）"
    input_schema = ReadChapterInput
    output_schema = ChapterContent

    async def run(self, input: ReadChapterInput, progress_callback=None) -> ChapterContent:
        try:
            from backend.config.config_loader import PROJECT_ROOT
            chapter_path = PROJECT_ROOT / f"data/{input.project_id}/chapters/chapter_{input.chapter_num:03d}.md"
            if not chapter_path.exists():
                return ToolError(
                    code="NOT_FOUND",
                    message=f"Chapter {input.chapter_num} not found",
                )
            content = chapter_path.read_text()
            # 提取标题（首行 # 开头）
            title = ""
            for line in content.split("\n"):
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            return ChapterContent(
                num=input.chapter_num,
                title=title or f"第 {input.chapter_num} 章",
                content=content,
                word_count=len(content),
                generated_at=datetime.fromtimestamp(chapter_path.stat().st_mtime).isoformat(),
            )
        except Exception as e:
            return ToolError(code="READ_FAILED", message=str(e))


register_tool(GenerateChapterTool())
register_tool(ReadChapterTool())
