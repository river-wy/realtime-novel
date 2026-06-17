"""AgentStateRepository: LangGraph checkpoint 持久化

对应 spec.md §4.1 + infra.md §B.3.4
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from realtime_novel.persistence.models import AgentState
from realtime_novel.persistence.sqlite_store import get_store


class AgentStateRepository:
    """LangGraph checkpoint 持久化（ON CONFLICT DO UPDATE）"""

    async def save_checkpoint(self, thread_id: str, checkpoint_data: dict) -> None:
        """保存或更新 checkpoint（ON CONFLICT(thread_id) DO UPDATE）"""
        with get_store().connection() as conn:
            conn.execute(
                """INSERT INTO agent_state (thread_id, checkpoint_data, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(thread_id) DO UPDATE SET
                     checkpoint_data = excluded.checkpoint_data,
                     updated_at = excluded.updated_at""",
                (thread_id, json.dumps(checkpoint_data), datetime.now()),
            )

    async def load_checkpoint(self, thread_id: str) -> Optional[dict]:
        """加载 checkpoint，不存在返回 None"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT checkpoint_data FROM agent_state WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["checkpoint_data"])

    async def list_threads(self, limit: int = 100) -> list[str]:
        """列出所有 thread_id（按 updated_at DESC）"""
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT thread_id FROM agent_state ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [r["thread_id"] for r in rows]
