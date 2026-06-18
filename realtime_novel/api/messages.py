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
    project_id: Optional[str] = None,
) -> str:
    """记录业务接口调用到 messages 表（role=tool）

    v0.5: 加 project_id 字段（每条消息绑 project，是"操作目标"）

    Args:
        conversation_id: 对话 ID
        tool_name: 工具名（如 'create_project'）
        args: 工具参数
        result: 工具返回（dict）
        project_id: v0.5 新增，操作目标 project

    Returns:
        message_id（新建的 message 主键）
    """
    if not conversation_id:
        return ""

    message_id = str(uuid.uuid4())
    tool_calls_json = json.dumps({"name": tool_name, "args": args}, ensure_ascii=False)
    tool_results_json = json.dumps(result, ensure_ascii=False, default=str)

    with get_store().connection() as conn:
        conn.execute(
            """INSERT INTO messages (
                id, conversation_id, project_id, role, content,
                tool_calls, tool_results, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                message_id, conversation_id, project_id, "tool", "",
                tool_calls_json, tool_results_json, _now(),
            ),
        )
        # 更新 conversation message_count
        conn.execute(
            "UPDATE conversations SET last_active_at = ?, message_count = message_count + 1 WHERE id = ?",
            (_now(), conversation_id),
        )

    return message_id


def record_assistant_message(
    conversation_id: str,
    content: str,
    tool_calls: Optional[Dict[str, Any]] = None,
    project_id: Optional[str] = None,
) -> str:
    """记录 assistant 回复（用于可选的"自然语言解释"）"""
    if not conversation_id:
        return ""
    message_id = str(uuid.uuid4())
    tool_calls_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
    with get_store().connection() as conn:
        conn.execute(
            """INSERT INTO messages (
                id, conversation_id, project_id, role, content, tool_calls, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (message_id, conversation_id, project_id, "assistant", content, tool_calls_json, _now()),
        )
        conn.execute(
            "UPDATE conversations SET last_active_at = ?, message_count = message_count + 1 WHERE id = ?",
            (_now(), conversation_id),
        )
    return message_id


def get_or_create_conversation(user_id: str, project_id: Optional[str] = None) -> str:
    """v0.5 完整版：user active conversation 一对一（同步实现）

    1.1 小说家 = 全局管家，不绑 project（project_id 参数保留向后兼容，不存）
    1.2 user-valid conversation 一对一（每个 user 只有 1 个 active）

    用纯 SQL 实现（不调 async），避免与 event loop 冲突
    """
    with get_store().connection() as conn:
        # 1. 查 user 当前 active
        row = conn.execute(
            """SELECT id FROM conversations
            WHERE user_id = ? AND status = 'active'
            ORDER BY created_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        if row:
            conv_id = row["id"]
            conn.execute(
                "UPDATE conversations SET last_active_at = ? WHERE id = ?",
                (_now(), conv_id),
            )
            return conv_id

        # 2. 没 active → 先 invalidate 旧的（理论上没 active，但防双保险）
        conn.execute(
            """UPDATE conversations
            SET status = 'invalidated', invalidated_at = ?, reason = 'auto'
            WHERE user_id = ? AND status = 'active'""",
            (_now(), user_id),
        )

        # 3. 创建新 active
        conv_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO conversations (
                id, user_id, created_at, last_active_at, status
            ) VALUES (?, ?, ?, ?, 'active')""",
            (conv_id, user_id, _now(), _now()),
        )
        return conv_id


def invalidate_conversation(conversation_id: str, reason: str = "user_new_chat") -> None:
    """v0.5 新增：作废 conversation（"新建对话"触发）"""
    with get_store().connection() as conn:
        conn.execute(
            """UPDATE conversations
            SET status = 'invalidated', invalidated_at = ?, reason = ?
            WHERE id = ?""",
            (_now(), reason, conversation_id),
        )
