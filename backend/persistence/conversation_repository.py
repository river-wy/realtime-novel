"""ConversationRepository：conversations + messages 表 CRUD"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from backend.persistence.models import (
    Conversation, Message, MessageRole, ConversationStatus,
)
from backend.persistence.sqlite_store import get_store


class ConversationRepository:
    """conversations + messages Repository"""

    # ============ Conversation CRUD ============

    async def get_active_conversation(self, user_id: str) -> Optional[Conversation]:
        """获取 user 当前 active conversation（最多 1 条）"""
        with get_store().connection() as conn:
            row = conn.execute(
                """SELECT * FROM conversations
                WHERE user_id = ? AND status = 'active'
                ORDER BY created_at DESC LIMIT 1""",
                (user_id,),
            ).fetchone()
        return self._row_to_conversation(row) if row else None

    async def get_or_create_active_conversation(self, user_id: str) -> Conversation:
        """获取或创建 active conversation"""
        conv = await self.get_active_conversation(user_id)
        if conv:
            return conv
        return await self.create_conversation(user_id)

    async def get_or_refresh_active_conversation(
        self, user_id: str, session_window_hours: int = 24
    ) -> Conversation:
        """24h 滑窗管理：距最后一条消息超过 24h 则 invalidate 旧 active 并新建

        使用 last_active_at（最后一次消息时间）而非 created_at，实现真正的滑动窗口：
        只要用户在 24h 内有消息活动，conversation 就持续有效。
        add_message 在每次写消息时会自动更新 last_active_at。
        """
        active = await self.get_active_conversation(user_id)
        if active:
            age = datetime.now() - active.last_active_at
            if age < timedelta(hours=session_window_hours):
                return active
            await self.invalidate_conversation(active.id, reason="stale_24h")
        return await self.create_conversation(user_id)

    async def create_conversation(self, user_id: str) -> Conversation:
        """创建新 active conversation（先 invalidate 旧 active）"""
        now = datetime.now()
        with get_store().connection() as conn:
            conn.execute(
                """UPDATE conversations
                SET status = 'invalidated', invalidated_at = ?
                WHERE user_id = ? AND status = 'active'""",
                (now, user_id),
            )
        conv = Conversation(
            id=str(uuid.uuid4()),
            user_id=user_id,
            created_at=now,
            last_active_at=now,
            status=ConversationStatus.ACTIVE,
        )
        with get_store().connection() as conn:
            conn.execute(
                """INSERT INTO conversations (
                    id, user_id, created_at, last_active_at, status
                ) VALUES (?, ?, ?, ?, ?)""",
                (conv.id, conv.user_id, conv.created_at, conv.last_active_at, conv.status.value),
            )
        return conv

    async def invalidate_conversation(
        self, conversation_id: str, reason: str = "user_new_chat"
    ) -> None:
        """把对话标 invalidated"""
        with get_store().connection() as conn:
            conn.execute(
                """UPDATE conversations
                SET status = 'invalidated', invalidated_at = ?
                WHERE id = ?""",
                (datetime.now(), conversation_id),
            )

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """按 ID 查对话"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return self._row_to_conversation(row) if row else None

    async def list_conversations(
        self, user_id: str, status: Optional[str] = None, limit: int = 50
    ) -> List[Conversation]:
        """列 user 的对话（可选按 status 过滤）"""
        with get_store().connection() as conn:
            if status:
                rows = conn.execute(
                    """SELECT * FROM conversations
                    WHERE user_id = ? AND status = ?
                    ORDER BY created_at DESC LIMIT ?""",
                    (user_id, status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM conversations
                    WHERE user_id = ?
                    ORDER BY created_at DESC LIMIT ?""",
                    (user_id, limit),
                ).fetchall()
        return [self._row_to_conversation(r) for r in rows]

    async def update_summary(self, conversation_id: str, summary: str) -> None:
        """更新对话 summary"""
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE conversations SET summary = ? WHERE id = ?",
                (summary, conversation_id),
            )

    # ============ Message CRUD ============

    async def add_message(
        self,
        conversation_id: str,
        role: MessageRole | str,
        content: Optional[str] = None,
        tool_calls: Optional[dict] = None,
        tool_results: Optional[dict] = None,
        project_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> Message:
        """添加消息 + 自动更新 last_active_at + message_count"""
        now = datetime.now()
        msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            project_id=project_id,
            role=MessageRole(role) if isinstance(role, str) else role,
            content=content,
            tool_calls=tool_calls,
            tool_results=tool_results,
            agent_name=agent_name,
            created_at=now,
        )
        with get_store().connection() as conn:
            conn.execute(
                """INSERT INTO messages (
                    id, conversation_id, project_id, role, content,
                    tool_calls, tool_results, agent_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    msg.id, msg.conversation_id, msg.project_id, msg.role.value, msg.content,
                    json.dumps(msg.tool_calls) if msg.tool_calls else None,
                    json.dumps(msg.tool_results) if msg.tool_results else None,
                    msg.agent_name,
                    msg.created_at,
                ),
            )
            conn.execute(
                """UPDATE conversations
                SET last_active_at = ?,
                    message_count = message_count + 1
                WHERE id = ?""",
                (now, conversation_id),
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

    async def get_messages_by_project(
        self, project_id: str, limit: int = 100
    ) -> list[Message]:
        """按 project_id 取历史"""
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE project_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    async def query_messages(
        self, conversation_id: str, keyword: str, limit: int = 1000
    ) -> list[Message]:
        """SQLite LIKE 关键词搜索"""
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? "
                "AND content LIKE ? LIMIT ?",
                (conversation_id, f"%{keyword}%", limit),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    # ============ helpers ============

    def _row_to_conversation(self, row) -> Conversation:
        if row is None:
            return None
        d = dict(row)
        return Conversation(
            id=d["id"],
            user_id=d["user_id"],
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
            last_active_at=datetime.fromisoformat(d["last_active_at"]) if isinstance(d["last_active_at"], str) else d["last_active_at"],
            status=ConversationStatus(d.get("status", "active")),
            invalidated_at=datetime.fromisoformat(d["invalidated_at"]) if d.get("invalidated_at") and isinstance(d["invalidated_at"], str) else d.get("invalidated_at"),
            summary=d.get("summary"),
            message_count=d.get("message_count", 0),
        )

    def _row_to_message(self, row) -> Message:
        d = dict(row)
        return Message(
            id=d["id"],
            conversation_id=d["conversation_id"],
            project_id=d.get("project_id"),
            role=MessageRole(d["role"]),
            content=d.get("content"),
            tool_calls=json.loads(d["tool_calls"]) if d.get("tool_calls") else None,
            tool_results=json.loads(d["tool_results"]) if d.get("tool_results") else None,
            agent_name=d.get("agent_name"),
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
        )
