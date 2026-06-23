"""ConversationRepository: conversations + messages 表的 CRUD (v0.5)

v0.5 落地：
- 1.1 小说家 = 全局管家，不绑 project（conversations.project_id 移除）
- 1.2 user-valid conversation 一对一（status + invalidate 机制）
- messages.project_id 新增（每条消息绑 project，是"操作目标"）

对应 spec.md §4.1 + infra.md §B.3.2
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional, List

from backend.persistence.models import (
    Conversation, Message, MessageRole, ConversationStatus,
)
from backend.persistence.sqlite_store import get_store


class ConversationRepository:
    """conversations + messages Repository (v0.5 完整版)"""

    # ============ Conversation CRUD ============

    async def get_active_conversation(self, user_id: str) -> Optional[Conversation]:
        """获取 user 当前 active conversation（v0.5: 一对一）

        Returns: 当前 active conversation（最多 1 条），None 表示无 active
        """
        with get_store().connection() as conn:
            row = conn.execute(
                """SELECT * FROM conversations
                WHERE user_id = ? AND status = 'active'
                ORDER BY created_at DESC LIMIT 1""",
                (user_id,),
            ).fetchone()
        return self._row_to_conversation(row) if row else None

    async def get_or_create_active_conversation(self, user_id: str) -> Conversation:
        """获取或创建 active conversation（一对一铁律）"""
        conv = await self.get_active_conversation(user_id)
        if conv:
            return conv
        return await self.create_conversation(user_id)

    async def create_conversation(self, user_id: str) -> Conversation:
        """创建新 active conversation（先 invalidate 旧 active）"""
        now = datetime.now()
        # 1. 先把当前 user 的所有 active conversation 标 invalidated
        with get_store().connection() as conn:
            conn.execute(
                """UPDATE conversations
                SET status = 'invalidated', invalidated_at = ?, reason = 'auto'
                WHERE user_id = ? AND status = 'active'""",
                (now, user_id),
            )
        # 2. 创建新 active
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
        """把对话标 invalidated（"新建对话"触发）"""
        with get_store().connection() as conn:
            conn.execute(
                """UPDATE conversations
                SET status = 'invalidated', invalidated_at = ?, reason = ?
                WHERE id = ?""",
                (datetime.now(), reason, conversation_id),
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

    async def update_summary(
        self, conversation_id: str, summary: str
    ) -> None:
        """更新对话 summary（v0.5 新增：对话压缩）"""
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
        thinking: Optional[dict] = None,
        project_id: Optional[str] = None,  # v0.5 新增
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
            thinking=thinking,
            created_at=now,
        )
        with get_store().connection() as conn:
            conn.execute(
                """INSERT INTO messages (
                    id, conversation_id, project_id, role, content,
                    tool_calls, tool_results, thinking, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    msg.id, msg.conversation_id, msg.project_id, msg.role.value, msg.content,
                    json.dumps(msg.tool_calls) if msg.tool_calls else None,
                    json.dumps(msg.tool_results) if msg.tool_results else None,
                    json.dumps(msg.thinking) if msg.thinking else None,
                    msg.created_at,
                ),
            )
            # 自动更新 last_active_at + message_count
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
        """按 project_id 取历史（v0.5 章节生成时用）"""
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
        """SQLite LIKE 关键词搜索（验收点 A5）"""
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
        # v0.5 字段可能不存在（v001/v002 老数据）— 兜底
        return Conversation(
            id=d["id"],
            user_id=d["user_id"],
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
            last_active_at=datetime.fromisoformat(d["last_active_at"]) if isinstance(d["last_active_at"], str) else d["last_active_at"],
            status=ConversationStatus(d.get("status", "active")),
            invalidated_at=datetime.fromisoformat(d["invalidated_at"]) if d.get("invalidated_at") and isinstance(d["invalidated_at"], str) else d.get("invalidated_at"),
            reason=d.get("reason"),
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
            thinking=json.loads(d["thinking"]) if d.get("thinking") else None,
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
        )
