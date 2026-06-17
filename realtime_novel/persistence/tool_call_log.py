"""ToolCallLogRepository: tool_calls_log 表的 CRUD

对应 spec.md §4.1 + infra.md §B.3.3
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from realtime_novel.persistence.models import ToolCallLog
from realtime_novel.persistence.sqlite_store import get_store


class ToolCallLogRepository:
    """工具调用审计 Repository"""

    async def add(
        self,
        tool_name: str,
        args: Optional[dict] = None,
        result: Optional[dict] = None,
        duration_ms: int = 0,
        message_id: Optional[str] = None,
    ) -> ToolCallLog:
        """记录一次工具调用"""
        log = ToolCallLog(
            id=str(uuid.uuid4()),
            message_id=message_id,
            tool_name=tool_name,
            args=args,
            result=result,
            duration_ms=duration_ms,
            created_at=datetime.now(),
        )
        with get_store().connection() as conn:
            conn.execute(
                "INSERT INTO tool_calls_log (id, message_id, tool_name, args, result, duration_ms, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    log.id, log.message_id, log.tool_name,
                    json.dumps(log.args) if log.args else None,
                    json.dumps(log.result) if log.result else None,
                    log.duration_ms, log.created_at,
                ),
            )
        return log

    async def list_by_tool(self, tool_name: str, limit: int = 100) -> list[ToolCallLog]:
        """查询某工具的所有调用（性能验收 §6.4 < 100ms）"""
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tool_calls_log WHERE tool_name = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (tool_name, limit),
            ).fetchall()
        return [self._row_to_log(r) for r in rows]

    async def list_by_message(self, message_id: str) -> list[ToolCallLog]:
        """查询某消息关联的所有工具调用"""
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tool_calls_log WHERE message_id = ? ORDER BY created_at",
                (message_id,),
            ).fetchall()
        return [self._row_to_log(r) for r in rows]

    def _row_to_log(self, row) -> ToolCallLog:
        return ToolCallLog(
            id=row["id"],
            message_id=row["message_id"],
            tool_name=row["tool_name"],
            args=json.loads(row["args"]) if row["args"] else None,
            result=json.loads(row["result"]) if row["result"] else None,
            duration_ms=row["duration_ms"],
            created_at=row["created_at"],
        )
