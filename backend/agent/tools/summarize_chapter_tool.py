"""summarize_chapter 工具

文笔家 ReAct loop 调这个工具抽取章节的 1 句话 summary。

设计：
- 输入：章节正文 (content)
- 输出：summary 字符串
- 解析策略（三层 fallback）:
  1. sentinel 块（###SUMMARY### ... ###END_SUMMARY###）— 文笔家在 prompt 里被要求输出
  2. fallback_truncate（取前 100 字截断）— sentinel 不存在时
  3. llm_fallback（调 LLM 单独生成）— 前两个都失败时（很少触发）
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.agent.tools.base import BaseTool, ToolError, register_tool
from backend.agent.tools.schemas import SummarizeChapterInput, SummarizeChapterOutput
from backend.agent.specialists.chapter_summarizer import (
    extract_summary_from_llm_output,
    parse_chapter_summary,
    fallback_summary,
)

log = logging.getLogger(__name__)


class SummarizeChapterTool(BaseTool):
    """抽取章节 1 句话 summary"""
    name = "summarize_chapter"
    description = (
        "从章节正文中抽取 1 句话 summary（~50-100 字）。"
        "优先解析 sentinel 块（###SUMMARY### ... ###END_SUMMARY###），"
        "失败则 fallback 到正文前 100 字截断，最后 LLM 单独生成。"
    )
    input_schema = SummarizeChapterInput
    output_schema = SummarizeChapterOutput

    async def run(
        self, input: SummarizeChapterInput, progress_callback=None
    ) -> SummarizeChapterOutput:
        try:
            content = input.content
            method = "sentinel"
            summary: Optional[str] = None

            # 1. sentinel 解析
            summary = extract_summary_from_llm_output(content)

            # 2. fallback: 取前 100 字截断
            if not summary:
                summary = fallback_summary(content, max_chars=100)
                method = "fallback_truncate"

            # 3. last resort: 调 LLM 单独生成
            if not summary or len(summary.strip()) < 5:
                summary = await self._llm_fallback(content, input.project_id)
                method = "llm_fallback"

            if not summary:
                return ToolError(
                    code="SUMMARY_FAILED",
                    message="无法从章节正文抽取 summary",
                )

            log.info(
                "summarize_chapter: project_id=%s, chapter_num=%s, "
                "method=%s, summary_len=%d",
                input.project_id, input.chapter_num, method, len(summary),
            )

            return SummarizeChapterOutput(
                summary=summary.strip(),
                method=method,
            )
        except Exception as e:
            log.error(
                "summarize_chapter 失败: project_id=%s, error=%s",
                input.project_id, e,
                exc_info=True,
            )
            return ToolError(code="SUMMARY_FAILED", message=str(e))

    async def _llm_fallback(self, content: str, project_id: str) -> Optional[str]:
        """当 sentinel 和 truncate 都失败时，调 LLM 单独生成 summary"""
        try:
            from backend.adapters import get_llm_adapter
            from backend.adapters.types import ModelRole

            adapter = get_llm_adapter()
            content_snippet = content[:3000]

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
                enable_thinking=False,
            )
            summary = response.content.strip()
            if summary:
                log.info(
                    "summarize_chapter: [%s] LLM fallback 生成成功, summary_len=%d",
                    project_id, len(summary),
                )
                return summary
        except Exception as e:
            log.warning(
                "summarize_chapter: [%s] LLM fallback 生成失败: %s",
                project_id, e,
            )
        return None


register_tool(SummarizeChapterTool())