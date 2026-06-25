"""novel_writer — 小说文笔家（v0.6 s3.4 AgentExecutor 接入）

职责（spec.md §3.2）：
1. 章节正文生成
2. Summary 抽取
3. 文风控制
4. 历史承接

实现：s3.4 起改用 AgentExecutor 跑 ReAct loop，LLM 自主决定调 search_memory / load_project / read_chapter
- 不再硬编码调用 ChapterGeneratorSpecialist
- LLM 可根据上下文决定先查记忆 / 先看上一章 / 直接生成

对应 spec.md §3.2
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from backend.agent.runtime.executor import AgentExecutor, AgentConfig, AgentOutput, get_agent_executor

log = logging.getLogger(__name__)


# ============ Writer 响应结构 ============

class ChapterOutput(BaseModel):
    """文笔家生成章节的输出"""
    chapter_content: str = ""
    chapter_summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    opinion: str = ""
    iterations: int = 0
    tool_calls_count: int = 0
    error: Optional[str] = None


# ============ 系统提示 ============

NOVEL_WRITER_SYSTEM_PROMPT = """你是「小说文笔家」。

【职责】
在 7 件基座（world_tree / style_charter / genre_resonance / main_plot / sub_plots / character_card / seed_table）的约束下，生成下一章小说正文。

【工作流】
1. 先调用 load_project 获取 7 件基座（理解约束）
2. 调用 read_chapter 读上一章（保持连贯性）
3. 可选调用 search_memory 检索相关历史记忆
4. 生成新章节正文（3000-4500 字）
5. 抽取 1-2 句 summary（放在正文末尾的 SUMMARY 块）
6. 把章节正文 + summary 作为 final_response 返回给管家

【输出格式】
正文直接是小说文字（不要 markdown 标题）。
最后加 SUMMARY 块：
```
SUMMARY: <一句话总结本章>
```

【关键约束】
- 严格遵守基座约束（角色设定、世界规则）
- 文风按 style_charter 调整
- 不修改任何基座（只读）
- 不决定剧情走向（走向由世界树管理维护）
"""


# ============ NovelWriter 主类 ============

class NovelWriter:
    """小说文笔家（v0.6 s3.4：AgentExecutor 接入）

    使用方式：
        writer = NovelWriter()
        output = await writer.generate_chapter(
            project_id="abc-123",
            user_message="继续写下一章",
        )
    """

    def __init__(self, executor: Optional[AgentExecutor] = None):
        self.executor = executor or get_agent_executor()

    async def generate_chapter(
        self,
        project_id: str,
        user_message: str = "请生成下一章",
        max_iterations: int = 7,
    ) -> ChapterOutput:
        """生成下一章

        Args:
            project_id: 项目 ID
            user_message: 用户提示
            max_iterations: ReAct loop 最大轮次（默认 7）

        Returns:
            ChapterOutput
        """
        cfg = AgentConfig(
            agent_name="novel_writer",
            system_prompt=NOVEL_WRITER_SYSTEM_PROMPT,
        )

        executor_output = await self.executor.execute(
            agent=cfg,
            user_message=user_message,
            project_id=project_id,
            max_iterations=max_iterations,
        )

        # 解析 final_response 中的正文和 summary
        chapter_content = executor_output.final_response
        chapter_summary = ""
        if "SUMMARY:" in chapter_content:
            parts = chapter_content.split("SUMMARY:", 1)
            chapter_content = parts[0].strip()
            chapter_summary = parts[1].strip() if len(parts) > 1 else ""

        return ChapterOutput(
            chapter_content=chapter_content,
            chapter_summary=chapter_summary,
            confidence=0.85 if not executor_output.error else 0.0,
            opinion=executor_output.final_response[:100],
            iterations=executor_output.iterations,
            tool_calls_count=len(executor_output.tool_calls_history),
            error=executor_output.error,
        )


# ============ 工厂方法 ============

_writer_instance: Optional[NovelWriter] = None


def get_novel_writer() -> NovelWriter:
    """获取单例 NovelWriter"""
    global _writer_instance
    if _writer_instance is None:
        _writer_instance = NovelWriter()
    return _writer_instance