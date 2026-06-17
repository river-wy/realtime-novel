"""ConversationRepository: conversations + messages 表的 CRUD

对应 spec.md §4.1 + infra.md §B.3.2
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from realtime_novel.persistence.models import Conversation, Message, MessageRole
from realtime_novel.persistence.sqlite_store import get_store


class ConversationRepository:
    """conversations + messages Repository"""

    async def create_conversation(
        self,
        user_id: str,
        project_id: Optional[str] = None,
    ) -> Conversation:
        """创建新对话线程"""
        now = datetime.now()
        conv = Conversation(
            id=str(uuid.uuid4()),
            project_id=project_id,
            user_id=user_id,
            created_at=now,
            last_active_at=now,
        )
        with get_store().connection() as conn:
            conn.execute(
                "INSERT INTO conversations (id, project_id, user_id, created_at, last_active_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv.id, conv.project_id, conv.user_id, conv.created_at, conv.last_active_at),
            )
        return conv

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """按 ID 查对话"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return Conversation(**dict(row)) if row else None

    async def add_message(
        self,
        conversation_id: str,
        role: MessageRole | str,
        content: Optional[str] = None,
        tool_calls: Optional[dict] = None,
        tool_results: Optional[dict] = None,
        thinking: Optional[dict] = None,
    ) -> Message:
        """添加消息 + 自动更新 last_active_at"""
        msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role=MessageRole(role) if isinstance(role, str) else role,
            content=content,
            tool_calls=tool_calls,
            tool_results=tool_results,
            thinking=thinking,
            created_at=datetime.now(),
        )
        with get_store().connection() as conn:
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, tool_calls, tool_results, thinking, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    msg.id, msg.conversation_id, msg.role.value, msg.content,
                    json.dumps(msg.tool_calls) if msg.tool_calls else None,
                    json.dumps(msg.tool_results) if msg.tool_results else None,
                    json.dumps(msg.thinking) if msg.thinking else None,
                    msg.created_at,
                ),
            )
            # 自动更新 last_active_at
            conn.execute(
                "UPDATE conversations SET last_active_at = ? WHERE id = ?",
                (msg.created_at, conversation_id),
            )
        return msg

    async def get_messages(
        self, conversation_id: str, limit: int = 100
    ) -> list[Message]:
        """按 created_at DESC 读取最近 N 条消息"""
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    async def query_messages(
        self, conversation_id: str, keyword: str, limit: int = 1000
    ) -> list[Message]:
        """SQLite LIKE 关键词搜索（验收点 A5）"""
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? "
                "AND content LIKE ? LIMIT ?",
                (conversation_id, f"%{keyword}%", limit),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def _row_to_message(self, row) -> Message:
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=MessageRole(row["role"]),
            content=row["content"],
            tool_calls=json.loads(row["tool_calls"]) if row["tool_calls"] else None,
            tool_results=json.loads(row["tool_results"]) if row["tool_results"] else None,
            thinking=json.loads(row["thinking"]) if row["thinking"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if isinstance(row["created_at"], str) else row["created_at"],
        )
