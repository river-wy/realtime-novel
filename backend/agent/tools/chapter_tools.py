"""Chapter 工具（generate_chapter / read_chapter）

v0.6.2 重构：
- generate_chapter: 只负责落盘（写文件 + 入 DB + 提取标题），不再调 LLM
  - LLM 在文笔家 ReAct loop 里写正文
  - 工具接收 content 字段 → 落盘
- read_chapter: 读章节正文（不变）

所有章节生成入口（页面按钮 / Onboarding Step 5 / 管家 ReAct）
都通过 delegate_chapter_generation() 委托给文笔家 ReAct loop，
最终调用 generate_chapter 工具落盘。

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
from backend.services.project_manager import ProjectManager
from backend.persistence import ChapterStatusRepository, ChapterState


class GenerateChapterTool(BaseTool):
    """v0.6.2 重构：纯落盘工具
    
    输入: LLM 在 ReAct loop 里写的章节正文 (content)
    输出: 落盘结果 (ChapterContent 含 num/title/content/word_count/generated_at/summary)
    
    不再调 LLM, 不再调 specialist. 落盘逻辑:
    1. 拿当前章节数 → next_num
    2. 写文件 (data/projects/{id}/chapters/chapter_NNN.md)
    3. 入 DB (ChapterRepository.create)
    4. 提取标题 (# 第 N 章 行)
    5. 返回结构化结果
    """
    name = "generate_chapter"
    description = "将文笔家写的章节正文落盘（写文件 + 入 DB + 提取标题）。同项目并发返回 409。"
    input_schema = GenerateChapterInput
    output_schema = ChapterContent

    def __init__(self):
        self._pm = ProjectManager()
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
                # 1. 拿当前章节数 → next_num
                proj = await self._pm.load(input.project_id)
                existing = proj.get("chapters", []) if proj else []
                next_chapter_num = len(existing) + 1

                # 2. 标 generating
                await self._status_repo.set_status(
                    input.project_id, next_chapter_num, ChapterState.GENERATING
                )
                if progress_callback:
                    await progress_callback({"step": "generating", "percentage": 10})

                # 3. 提取标题（首行 # 开头）
                chapter_content = input.content
                chapter_title = f"第 {next_chapter_num} 章"
                for line in chapter_content.split("\n"):
                    line = line.strip()
                    if line.startswith("# "):
                        chapter_title = line[2:].strip()
                        break

                # 4. 写文件
                from backend.config.config_loader import PROJECT_ROOT
                from backend.persistence import ChapterRepository
                
                chapters_dir = PROJECT_ROOT / f"data/projects/{input.project_id}/chapters"
                chapters_dir.mkdir(parents=True, exist_ok=True)
                chapter_path = chapters_dir / f"chapter_{next_chapter_num:03d}.md"
                chapter_path.write_text(chapter_content, encoding="utf-8")

                # 5. 入 DB
                chap_repo = ChapterRepository()
                chap_repo.create(
                    project_id=input.project_id,
                    chapter_num=next_chapter_num,
                    file_path=str(chapter_path),
                    title=chapter_title,
                    content_text=None,
                    word_count=len(chapter_content),
                    intervention=input.intervention,
                    summary=None,  # 由文笔家在 ReAct loop 里调 summarize_chapter 工具填
                )

                # 6. 标 done
                await self._status_repo.set_status(
                    input.project_id, next_chapter_num, ChapterState.DONE
                )
                if progress_callback:
                    await progress_callback({"step": "done", "percentage": 100})

                return ChapterContent(
                    num=next_chapter_num,
                    title=chapter_title,
                    content=chapter_content,
                    word_count=len(chapter_content),
                    generated_at=datetime.now().isoformat(),
                    summary=None,  # 由文笔家在 ReAct loop 里调 summarize_chapter 工具填
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