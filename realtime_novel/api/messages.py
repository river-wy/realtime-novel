"""messages 写入辅助 — v0.4.1 业务接口落库 record_tool_call

讨论 6.2 拍板：业务接口调用后写 messages（role=tool, tool_call={name, args, result}）
管家 LLM 下次调用拼 messages 时自动包含
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from realtime_novel.persistence import get_store


def _now() -> datetime:
    return datetime.now()


def record_tool_call(
    conversation_id: str,
    tool_name: str,
    args: Dict[str, Any],
    result: Dict[str, Any],
) -> str:
    """记录业务接口调用到 messages 表（role=tool）

    Args:
        conversation_id: 对话 ID
        tool_name: 工具名（如 'create_project'）
        args: 工具参数
        result: 工具返回（dict）

    Returns:
        message_id（新建的 message 主键）
    """
    if not conversation_id:
        # 没有 conversation_id 就跳过（某些路由不绑对话）
        return ""

    message_id = str(uuid.uuid4())
    tool_calls_json = json.dumps({"name": tool_name, "args": args}, ensure_ascii=False)
    tool_results_json = json.dumps(result, ensure_ascii=False, default=str)

    with get_store().connection() as conn:
        conn.execute(
            """INSERT INTO messages (
                id, conversation_id, role, content,
                tool_calls, tool_results, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                message_id, conversation_id, "tool", "",
                tool_calls_json, tool_results_json, _now(),
            ),
        )

    return message_id


def record_assistant_message(
    conversation_id: str,
    content: str,
    tool_calls: Optional[Dict[str, Any]] = None,
) -> str:
    """记录 assistant 回复（用于可选的"自然语言解释"）"""
    if not conversation_id:
        return ""
    message_id = str(uuid.uuid4())
    tool_calls_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
    with get_store().connection() as conn:
        conn.execute(
            """INSERT INTO messages (
                id, conversation_id, role, content, tool_calls, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (message_id, conversation_id, "assistant", content, tool_calls_json, _now()),
        )
    return message_id


def get_or_create_conversation(user_id: str, project_id: Optional[str] = None) -> str:
    """获取/创建 user 当前 active conversation（v0.5 完整落地，v0.4.1 简化）

    简化版：每个 (user_id, project_id) 组合 1 个 conversation
    """
    with get_store().connection() as conn:
        row = conn.execute(
            """SELECT id FROM conversations
            WHERE user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))
            ORDER BY last_active_at DESC LIMIT 1""",
            (user_id, project_id, project_id),
        ).fetchone()
        if row:
            conv_id = row["id"]
            conn.execute(
                "UPDATE conversations SET last_active_at = ? WHERE id = ?",
                (_now(), conv_id),
            )
            return conv_id

        conv_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO conversations (id, project_id, user_id, created_at, last_active_at)
            VALUES (?, ?, ?, ?, ?)""",
            (conv_id, project_id, user_id, _now(), _now()),
        )
        return conv_id
