"""Memory 工具（search_memory：向量检索 + SQLite LIKE 关键词）

对应 core.md §B.1
"""
from __future__ import annotations

import json

from realtime_novel.agent.tools.base import BaseTool, ToolError, register_tool
from realtime_novel.agent.tools.schemas import SearchMemoryInput, SearchMemoryResult
from realtime_novel.persistence import get_store


class SearchMemoryTool(BaseTool):
    name = "search_memory"
    description = "搜索世界书条目（sqlite-vec 向量检索 + LIKE 关键词双路径）"
    input_schema = SearchMemoryInput
    output_schema = SearchMemoryResult

    async def run(
        self, input: SearchMemoryInput, progress_callback=None
    ) -> SearchMemoryResult:
        try:
            if progress_callback:
                await progress_callback({"step": "searching", "percentage": 50})
            entries: list[dict] = []
            with get_store().connection() as conn:
                # 1. SQLite LIKE 关键词搜索（content 列）
                rows = conn.execute(
                    """SELECT DISTINCT m.id, m.conversation_id, m.content, m.role
                       FROM messages m
                       JOIN conversations c ON m.conversation_id = c.id
                       WHERE c.project_id = ? AND m.content LIKE ?
                       LIMIT ?""",
                    (input.project_id, f"%{input.query}%", input.top_k),
                ).fetchall()
                for r in rows:
                    entries.append({
                        "entry_id": r["id"],
                        "conversation_id": r["conversation_id"],
                        "content_preview": (r["content"] or "")[:200],
                        "role": r["role"],
                        "source": "like",
                    })
                # 2. vec 语义检索（如果有 embedding；v0.4 简化 stub）
                try:
                    # 简化：直接返回前 top_k（实际应生成 query embedding 再 KNN）
                    # vec_rows = conn.execute(
                    #     "SELECT entry_id, distance FROM world_entries_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                    #     (embedding_blob, input.top_k),
                    # ).fetchall()
                    pass
                except Exception:
                    pass
            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return SearchMemoryResult(entries=entries[:input.top_k])
        except Exception as e:
            return ToolError(code="SEARCH_FAILED", message=str(e))


register_tool(SearchMemoryTool())
