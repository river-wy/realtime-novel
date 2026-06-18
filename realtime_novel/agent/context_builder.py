"""context_builder — v0.4.1 多轮上下文组装

从 conversation_id 取历史 messages → 拼成 OpenAI 格式数组

Usage:
    from realtime_novel.agent.context_builder import build_messages_for_node
    msgs = build_messages_for_node(conversation_id, current_user_msg, max_history=10)
    # msgs = [{'role': 'user', 'content': '...'}, {'role': 'assistant', '...'}, ...]
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional

from realtime_novel.persistence import get_store


def _row_to_message(row: dict) -> Optional[Dict[str, Any]]:
    """DB message row → OpenAI 格式 message

    支持 4 种 role：
    - user: content 字符串
    - assistant: content（可空，tool_calls 序列化）
    - tool: content（tool_results 序列化）
    - system: content 字符串
    """
    role = row.get("role")
    content = row.get("content") or ""

    if role == "tool":
        # tool 消息：content 包含 tool_results（业务接口调用后落库）
        tool_results = row.get("tool_results")
        if tool_results:
            # 解析 JSON 字符串
            import json
            try:
                results = json.loads(tool_results) if isinstance(tool_results, str) else tool_results
            except Exception:
                results = tool_results
            content = f"[工具调用: {row.get('tool_calls', '')[:200]}]\n结果: {str(results)[:500]}"
        return {"role": "tool", "content": content}

    if role == "assistant":
        msg = {"role": "assistant", "content": content}
        # 如果有 tool_calls 字段，附上
        tool_calls = row.get("tool_calls")
        if tool_calls:
            import json
            try:
                tc = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
                msg["tool_calls"] = tc
            except Exception:
                pass
        return msg

    # user / system
    return {"role": role, "content": content}


def load_history_messages(
    conversation_id: str,
    max_history: int = 10,
    exclude_message_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """从 messages 表取历史 N 条（按 created_at 升序），转 OpenAI 格式

    Args:
        conversation_id: 对话 ID
        max_history: 最多取 N 条最近的
        exclude_message_id: 排除某条（当前 user message 已经在 messages 里时排除）
    """
    with get_store().connection() as conn:
        # 取最近 N 条
        rows = conn.execute(
            """SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT ?""",
            (conversation_id, max_history),
        ).fetchall()

    # 升序排
    rows = list(rows)[::-1]

    messages = []
    for r in rows:
        d = dict(r)
        if exclude_message_id and d.get("id") == exclude_message_id:
            continue
        msg = _row_to_message(d)
        if msg:
            messages.append(msg)

    return messages


def build_messages_for_node(
    conversation_id: str,
    current_user_message: str,
    max_history: int = 10,
    system_prompt: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """构建完整 messages 数组（system + 历史 + 当前 user）

    用法：
        msgs = build_messages_for_node(conv_id, user_msg, max_history=20)
        request = LLMRequest(prompt="", messages=msgs, system_prompt=管家prompt)
    """
    messages = []

    # 1. system（如果有）
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # 2. 历史
    history = load_history_messages(conversation_id, max_history=max_history)
    messages.extend(history)

    # 3. 当前 user message（追加到最后）
    messages.append({"role": "user", "content": current_user_message})

    return messages


def messages_to_openai_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """context_builder 内部用：把带 sentinel 的 messages 转纯 OpenAI 格式"""
    return messages
