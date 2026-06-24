"""novel_writer — 小说文笔家（v0.6 顶层 Agent 之一）

职责（对应 spec.md §3.2）：
1. 章节正文生成（在 7 件基座约束下）
2. Summary 抽取
3. 文风控制（按 style_charter）
4. 历史承接（基于已有章节 history）

关键设计：
- 不决定剧情走向（走向由世界树基座约束，基座由世界树管理维护）
- 不修改任何基座（只读）
- 调用 MemoryKeeper（内部工具）检索历史章节上下文
- 复用 specialists.ChapterGeneratorSpecialist 的 LLM 调用逻辑

对应 spec.md §3.2
"""
from __future__ import annotations

import logging
from typing import Optional
from pydantic import BaseModel, Field

from backend.agent.specialists import ChapterGeneratorSpecialist

log = logging.getLogger(__name__)


# ============ Writer 响应结构 ============

class ChapterOutput(BaseModel):
    """文笔家生成章节的输出"""
    chapter_content: str = ""
    chapter_summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    opinion: str = ""
    error: Optional[str] = None


class NovelWriter:
    """小说文笔家（v0.6 顶层 Agent）

    使用方式：
        writer = NovelWriter()
        result = await writer.generate_chapter(
            project_id="abc123",
            user_message="继续写下一章",
        )
        # result.chapter_content, result.chapter_summary

    v0.6 s2 阶段：调用 specialists.ChapterGeneratorSpecialist，封装为新接口
    v0.6 s3 阶段：会扩展 MemoryKeeper 调用、summary 增强等
    """

    def __init__(self):
        # 复用现有 specialist（v0.5 已实装的 ChapterGeneratorSpecialist）
        self.chapter_specialist = ChapterGeneratorSpecialist()

    async def generate_chapter(
        self,
        project_id: str,
        user_message: str = "请生成下一章",
        max_history: int = 5,
    ) -> ChapterOutput:
        """生成下一章

        Args:
            project_id: 项目 ID
            user_message: 用户提示（可选）
            max_history: 历史章节数

        Returns:
            ChapterOutput
        """
        log.info(f"novel_writer: generating chapter project_id={project_id}")

        try:
            # 委托给 ChapterGeneratorSpecialist（v0.5 已实装）
            specialist_result = await self.chapter_specialist.consult({
                "project_id": project_id,
                "user_message": user_message,
                "max_history": max_history,
            })

            return ChapterOutput(
                chapter_content=specialist_result.get("chapter_content", ""),
                chapter_summary=specialist_result.get("chapter_summary", ""),
                confidence=specialist_result.get("confidence", 0.0),
                opinion=specialist_result.get("opinion", ""),
                error=specialist_result.get("error"),
            )
        except Exception as e:
            log.error(f"novel_writer: generate_chapter failed: {e}")
            return ChapterOutput(
                confidence=0.0,
                opinion=f"章节生成失败: {e}",
                error=str(e),
            )


# ============ 工厂方法 ============

_writer_instance: Optional[NovelWriter] = None


def get_novel_writer() -> NovelWriter:
    """获取单例 NovelWriter"""
    global _writer_instance
    if _writer_instance is None:
        _writer_instance = NovelWriter()
    return _writer_instance