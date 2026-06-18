"""context_builder — v0.5 多轮上下文组装（按角色裁剪）

v0.4.1 基础版：从 messages 表拿 history + 拼 current user
v0.5 完整版：按角色裁剪 messages（讨论 3.2 拍板）

3 个角色的 messages 拼装：
- 小说家 (user 维度, 不绑 project):
    [system: 管家引导, history: 最近 10-20 轮 user/assistant, summary: 对话压缩, current: user msg]
- 架构师 (per-project):
    [system: 世界树管理, world_tree: 完整 JSON, chapter_summaries: 所有 1 句 × N, history: 最近 3-5 轮, current: user msg]
- 文笔家 (per-project):
    [system: 章节生成, world_tree: 基座, chapter_summaries: 分级结构 (20 章前 1 句, 20 章内 100-200 字), history: 最近 3-5 轮, current: user msg]
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Literal

from realtime_novel.persistence import get_store, ProjectRepository, ChapterRepository


# ============ v0.4.1 基础 ============

def _row_to_message(row: dict) -> Optional[Dict[str, Any]]:
    """DB message row → OpenAI 格式 message"""
    role = row.get("role")
    content = row.get("content") or ""

    if role == "tool":
        tool_results = row.get("tool_results")
        if tool_results:
            import json
            try:
                results = json.loads(tool_results) if isinstance(tool_results, str) else tool_results
            except Exception:
                results = tool_results
            content = f"[工具调用: {row.get('tool_calls', '')[:200]}]\n结果: {str(results)[:500]}"
        return {"role": "tool", "content": content}

    if role == "assistant":
        msg = {"role": "assistant", "content": content}
        tool_calls = row.get("tool_calls")
        if tool_calls:
            import json
            try:
                tc = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
                msg["tool_calls"] = tc
            except Exception:
                pass
        return msg

    return {"role": role, "content": content}


def load_history_messages(
    conversation_id: str,
    max_history: int = 10,
    exclude_message_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """从 messages 表取历史 N 条（按 created_at 升序），转 OpenAI 格式"""
    with get_store().connection() as conn:
        rows = conn.execute(
            """SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT ?""",
            (conversation_id, max_history),
        ).fetchall()
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


# ============ v0.5 完整版（按角色裁剪）============


def _load_project_data(project_id: str) -> Dict[str, Any]:
    """加载项目所有 7 件基座 + 章节 metadata

    Returns:
        {
            "world_tree": {...},
            "style_charter": {...},
            "genre_resonance": {...},
            "main_plot": {...},
            "sub_plot": {...},
            "character_card": {...},
            "seed_table": {...},
            "chapters": [ChapterRow, ...],
        }
    """
    proj_repo = ProjectRepository()
    chap_repo = ChapterRepository()

    artifacts = proj_repo.load_all_artifacts(project_id)
    chapters = chap_repo.list_by_project(project_id, limit=200)
    return {**artifacts, "chapters": chapters}


def _format_chapter_summaries_short(chapters: list, limit: int = 100) -> str:
    """把所有章节的 1 句话 summary 拼成一段（架构师用）"""
    lines = []
    for ch in chapters[:limit]:
        if ch.summary:
            lines.append(f"- 第{ch.chapter_num}章: {ch.summary}")
    return "\n".join(lines) if lines else "（暂无章节 summary）"


def _format_chapter_summaries_graded(chapters: list, detailed_window: int = 20) -> str:
    """章节 summary 分级结构（文笔家用）—— 讨论 3.2 欧尼酱洞察

    - 20 章之前：1 句话 summary（~20-30 tokens/章）
    - 20 章以内（最近 20 章）：detailed_summary（100-200 字/章）
    - 总输入 ~ 3000 tokens
    """
    lines = []
    n = len(chapters)
    # 按 chapter_num 升序
    sorted_chs = sorted(chapters, key=lambda c: c.chapter_num)
    for ch in sorted_chs:
        if ch.chapter_num <= n - detailed_window:
            # 20 章之前：用 1 句
            if ch.summary:
                lines.append(f"- 第{ch.chapter_num}章: {ch.summary}")
        else:
            # 20 章以内：用 detailed
            if ch.detailed_summary:
                lines.append(f"- 第{ch.chapter_num}章: {ch.detailed_summary}")
            elif ch.summary:
                lines.append(f"- 第{ch.chapter_num}章: {ch.summary}")
    return "\n".join(lines) if lines else "（暂无章节 summary）"


def _format_world_tree_compact(world_tree: dict) -> str:
    """压缩 world_tree 为字符串（架构师/文笔家用）"""
    if not world_tree:
        return "（世界树为空）"
    base = world_tree.get("base", {}) or {}
    timeline = base.get("timeline", {}) or {}
    geography = base.get("geography", {}) or {}
    core_rules = base.get("core_rules", []) or []

    parts = []
    if timeline.get("era"):
        parts.append(f"时代: {timeline['era']}")
    if timeline.get("anchor_event"):
        parts.append(f"锚定事件: {timeline['anchor_event']}")
    if geography.get("primary"):
        parts.append(f"主场景: {geography['primary']}")
    if core_rules:
        rules_str = "; ".join([f"{r.get('id', '')}: {r.get('statement', '')}" for r in core_rules[:5]])
        parts.append(f"核心规则: {rules_str}")
    return "\n".join(parts) if parts else "（世界树无核心信息）"


# ============ 3 个角色的 messages 拼装 ============


def build_messages_for_steward(
    user_id: str,
    current_user_message: str,
    system_prompt: str,
    max_history: int = 20,
) -> List[Dict[str, Any]]:
    """小说家（user 维度管家）的 messages

    结构：
    1. system: 管家引导 prompt
    2. history: 最近 10-20 轮 user/assistant/tool 消息
    3. summary: 对话压缩 summary（如果有）
    4. current: user message
    """
    messages = []

    # 1. system
    messages.append({"role": "system", "content": system_prompt})

    # 2. 拿 user 当前 active conversation 的 history
    from realtime_novel.persistence import ConversationRepository
    import asyncio
    repo = ConversationRepository()

    async def _get_active_conv_id():
        conv = await repo.get_active_conversation(user_id)
        return conv.id if conv else None

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在 event loop 里 → 用 thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as ex:
                conv_id = ex.submit(asyncio.run, _get_active_conv_id()).result()
        else:
            conv_id = asyncio.run(_get_active_conv_id())
    except RuntimeError:
        conv_id = asyncio.run(_get_active_conv_id())

    if conv_id:
        history = load_history_messages(conv_id, max_history=max_history)
        # 2. history
        messages.extend(history)
        # 3. summary（如果有）
        from realtime_novel.persistence import ConversationRepository as CR
        from realtime_novel.persistence import get_store as gs
        with gs().connection() as conn:
            row = conn.execute(
                "SELECT summary FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            if row and row["summary"]:
                # 插在 history 之前
                messages.insert(1, {
                    "role": "system",
                    "content": f"历史对话摘要: {row['summary']}",
                })

    # 4. current user message
    messages.append({"role": "user", "content": current_user_message})
    return messages


def build_messages_for_worldtree_keeper(
    project_id: str,
    current_user_message: str,
    system_prompt: str,
    max_history: int = 5,
) -> List[Dict[str, Any]]:
    """架构师（per-project 世界树管理）的 messages

    结构：
    1. system: 世界树管理 prompt
    2. world_tree: 完整 JSON
    3. chapter_summaries: 所有章节 1 句 × N（300 章 = 300 句，10-20K tokens）
    4. history: 最近 3-5 轮 user/assistant 消息
    5. current: user message
    """
    messages = []
    messages.append({"role": "system", "content": system_prompt})

    # 加载项目数据
    data = _load_project_data(project_id)
    world_tree = data.get("01-world-tree.yaml", {})
    chapters = data.get("chapters", [])

    # 2. world_tree
    messages.append({
        "role": "user",
        "content": f"## 世界树完整数据\n{json_dumps(world_tree)}",
    })
    # 3. chapter_summaries
    messages.append({
        "role": "user",
        "content": f"## 所有章节 1 句 summary\n{_format_chapter_summaries_short(chapters, limit=300)}",
    })
    # 4. history (project 维度，按 messages.project_id 过滤)
    history = _load_project_history(project_id, max_history=max_history)
    messages.extend(history)

    # 5. current
    messages.append({"role": "user", "content": current_user_message})
    return messages


def build_messages_for_chapter_generator(
    project_id: str,
    current_user_message: str,
    system_prompt: str,
    max_history: int = 5,
) -> List[Dict[str, Any]]:
    """文笔家（per-project 章节生成）的 messages

    结构：
    1. system: 章节生成 prompt
    2. world_tree: 基座数据
    3. chapter_summaries: 分级结构（20 章前 1 句，20 章内 detailed）
    4. history: 最近 3-5 轮 user/assistant 消息
    5. current: user message
    """
    messages = []
    messages.append({"role": "system", "content": system_prompt})

    data = _load_project_data(project_id)
    world_tree = data.get("01-world-tree.yaml", {})
    chapters = data.get("chapters", [])

    # 2. world_tree 基座
    messages.append({
        "role": "user",
        "content": f"## 世界树基座\n{_format_world_tree_compact(world_tree)}",
    })
    # 3. chapter_summaries 分级结构
    messages.append({
        "role": "user",
        "content": f"## 章节 summary 分级（20 章前 1 句，20 章内 detailed）\n{_format_chapter_summaries_graded(chapters, detailed_window=20)}",
    })
    # 4. history
    history = _load_project_history(project_id, max_history=max_history)
    messages.extend(history)

    # 5. current
    messages.append({"role": "user", "content": current_user_message})
    return messages


def _load_project_history(project_id: str, max_history: int = 5) -> List[Dict[str, Any]]:
    """按 project_id 取历史（per-project 维度）"""
    with get_store().connection() as conn:
        rows = conn.execute(
            """SELECT * FROM messages
            WHERE project_id = ? AND role IN ('user', 'assistant')
            ORDER BY created_at DESC
            LIMIT ?""",
            (project_id, max_history),
        ).fetchall()
    rows = list(rows)[::-1]
    return [_row_to_message(dict(r)) for r in rows if _row_to_message(dict(r))]


def json_dumps(obj: Any) -> str:
    """安全的 JSON dump"""
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


# ============ v0.4.1 兼容（保留旧 API）============

def build_messages_for_node(
    conversation_id: str,
    current_user_message: str,
    max_history: int = 10,
    system_prompt: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """v0.4.1 兼容 API（不推荐用于新代码）

    仍支持老调用：conversation_id + current_user_message
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    history = load_history_messages(conversation_id, max_history=max_history)
    messages.extend(history)
    messages.append({"role": "user", "content": current_user_message})
    return messages
