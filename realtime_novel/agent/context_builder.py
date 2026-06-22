"""context_builder — 多轮上下文组装（按角色裁剪）

3 个角色的 messages 拼装：
- 小说家 (user 维度, 不绑 project):
    [system: 管家引导, history: 最近 10-20 轮 user/assistant, summary: 对话压缩, current: user msg]
- 架构师 (per-project):
    [system: 世界树管理, world_tree: 完整 JSON, chapter_summaries: 所有 1 句 × N, history: 最近 3-5 轮, current: user msg]
- 文笔家 (per-project):
    [system: 章节生成, world_tree: 基座, chapter_summaries: 分级结构 (20 章前 1 句, 20 章内 100-200 字), history: 最近 3-5 轮, current: user msg]
"""
from __future__ import annotations

import json
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


# s1.4 新增: 5 个 helper 格式化 7 件基座其余字段

def _format_style_charter(style_charter: dict) -> str:
    """压缩 style_charter 为字符串（文笔家用）

    包含: prose_style / tone / density / taboos / notes / limits
    """
    if not style_charter or not isinstance(style_charter, dict):
        return "（文风宪法为空）"

    parts = []

    prose = style_charter.get('prose_style', {}) or {}
    if prose.get('primary'):
        prose_parts = [prose['primary']]
        if prose.get('sentence_length'):
            prose_parts.append(f"句式={prose['sentence_length']}")
        if prose.get('paragraph_style'):
            prose_parts.append(f"段落={prose['paragraph_style']}")
        parts.append("文风: " + " · ".join(prose_parts))

    tone = style_charter.get('tone', {}) or {}
    if tone.get('primary'):
        tone_parts = [tone['primary']]
        if tone.get('psychological_per_paragraph'):
            tone_parts.append(f"心理活动≤{tone['psychological_per_paragraph']}句/段")
        parts.append("基调: " + " · ".join(tone_parts))

    # density
    density = style_charter.get('density', {}) or {}
    if density:
        density_str = ", ".join([f"{k}={v}" for k, v in density.items() if v is not None])
        if density_str:
            parts.append(f"密度: {density_str}")

    # taboos (Step 3 用户填)
    taboos = style_charter.get('taboos', []) or []
    if taboos:
        taboo_strs = []
        for t in taboos:
            if isinstance(t, dict):
                taboo_strs.append(t.get('text') or t.get('statement', ''))
            elif isinstance(t, str):
                taboo_strs.append(t)
        taboo_strs = [s for s in taboo_strs if s]
        if taboo_strs:
            parts.append(f"禁区: {'; '.join(taboo_strs)}")

    # notes (Step 1 styles + Step 3 emotional_anchor)
    notes = style_charter.get('notes', []) or []
    notes_strs = [str(n) for n in notes if n]
    if notes_strs:
        parts.append(f"备注: {'; '.join(notes_strs)}")

    # limits
    limits = style_charter.get('limits', {}) or {}
    if limits:
        limits_str = ", ".join([f"{k}={v}" for k, v in limits.items() if v is not None])
        if limits_str:
            parts.append(f"限制: {limits_str}")

    return "\n".join(parts) if parts else "（文风宪法无具体内容）"


def _format_main_plot(main_plot: dict) -> str:
    """压缩 main_plot 为字符串（文笔家用）

    包含: arc_phrase (Step 4 main_conflict) + beats (Step 4 拆的节奏)
    """
    if not main_plot or not isinstance(main_plot, dict):
        return "（主线为空）"

    parts = []

    arc = main_plot.get('arc_phrase')
    if arc:
        parts.append(f"核心弧光: {arc}")

    beats = main_plot.get('beats', []) or []
    if beats:
        parts.append("节奏:")
        for b in beats[:10]:
            title = b.get('title', '')
            desc = b.get('description', '')
            status = b.get('status', '')
            chapter_range = b.get('chapter_range', {})
            cr_str = ""
            if chapter_range and 'start' in chapter_range:
                cr_str = f" [ch{chapter_range.get('start', '?')}-{chapter_range.get('end', '?')}]"
            line = f"  - {title}"
            if desc:
                line += f": {desc[:80]}"
            if status:
                line += f" ({status})"
            line += cr_str
            parts.append(line)

    return "\n".join(parts) if parts else "（主线无具体内容）"


def _format_sub_plot(threads: list) -> str:
    """压缩 sub_plot threads 为字符串（文笔家用）

    threads: list[dict] from sub_plot.threads[]
    """
    if not threads:
        return "（支线为空）"
    lines = []
    for t in threads[:10]:
        title = t.get('title', '')
        desc = t.get('description', '')
        status = t.get('status', '')
        priority = t.get('priority', '')
        line = f"- {title}"
        if desc:
            line += f": {desc[:80]}"
        if status:
            line += f" [{status}]"
        if priority:
            line += f" ({priority})"
        lines.append(line)
    return "\n".join(lines) if lines else "（支线无具体内容）"


def _format_characters(characters: list) -> str:
    """压缩 character_card characters 为字符串（文笔家用）

    characters: list[dict] from character_card.characters[]
    字段: name, role, background, traits, speech_style, arc
    """
    if not characters:
        return "（人物为空）"
    lines = []
    for c in characters[:15]:
        name = c.get('name', '?')
        role = c.get('role', '')
        background = c.get('background', '')
        traits = c.get('traits', []) or []
        speech = c.get('speech_style', '')

        line = f"- {name}"
        if role:
            line += f" ({role})"
        line += ":"
        if background:
            line += f"\n  背景: {background[:100]}"
        if traits:
            line += f"\n  特征: {', '.join(traits[:5])}"
        if speech:
            line += f"\n  说话风格: {speech[:50]}"
        lines.append(line)
    return "\n\n".join(lines) if lines else "（人物无具体内容）"


def _format_seeds(seeds: list) -> str:
    """压缩 seed_table seeds 为字符串（文笔家用）

    seeds: list[dict] from seed_table.seeds[]
    字段: id, content, importance, size, orientation, status
    """
    if not seeds:
        return "（种子为空）"
    lines = []
    for s in seeds[:20]:
        content = s.get('content', '')
        importance = s.get('importance', {}) or {}
        size = s.get('size', '')
        orientation = s.get('orientation', '')
        status = s.get('status', '')

        imp_str = importance.get('primary', '') if isinstance(importance, dict) else str(importance)
        line = f"- {content[:80]}"
        meta_parts = []
        if imp_str:
            meta_parts.append(imp_str)
        if size:
            meta_parts.append(size)
        if orientation:
            meta_parts.append(orientation)
        if status:
            meta_parts.append(status)
        if meta_parts:
            line += f" [{', '.join(meta_parts)}]"
        lines.append(line)
    return "\n".join(lines) if lines else "（种子无具体内容）"


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
    2. world_tree: 基座 (叙事核心)
    3. style_charter: 文风宪法 (基调/禁区/密度)  [s1.4 新增]
    4. main_plot: 主线 (核心矛盾/节奏)             [s1.4 新增]
    5. sub_plot: 支线                              [s1.4 新增]
    6. character_card: 人物                        [s1.4 新增]
    7. seed_table: 种子                            [s1.4 新增]
    8. chapter_summaries: 分级结构 (20 章前 1 句, 20 章内 detailed)
    9. history: 最近 3-5 轮 user/assistant 消息
    10. current: user message
    """
    messages = []
    messages.append({"role": "system", "content": system_prompt})

    data = _load_project_data(project_id)
    world_tree = data.get("01-world-tree.yaml", {})
    style_charter = data.get("02-style-charter.yaml", {})
    main_plot_raw = data.get("04-main-plot.yaml", {})
    sub_plot_raw = data.get("05-sub-plot.yaml", {})
    character_card = data.get("06-character-card.yaml", {})
    seed_table = data.get("07-seed-table.yaml", {})
    chapters = data.get("chapters", [])

    # 2. world_tree 基座
    messages.append({
        "role": "user",
        "content": f"## 世界树基座\n{_format_world_tree_compact(world_tree)}",
    })
    # 3. style_charter 文风宪法 (s1.4 新增)
    if style_charter:
        messages.append({
            "role": "user",
            "content": f"## 文风宪法\n{_format_style_charter(style_charter)}",
        })
    # 4. main_plot 主线 (s1.4 新增)
    if main_plot_raw and (main_plot_raw.get('arc_phrase') or main_plot_raw.get('beats')):
        messages.append({
            "role": "user",
            "content": f"## 主线剧情\n{_format_main_plot(main_plot_raw)}",
        })
    # 5. sub_plot 支线 (s1.4 新增)
    threads = sub_plot_raw.get('threads', []) if isinstance(sub_plot_raw, dict) else []
    if threads:
        messages.append({
            "role": "user",
            "content": f"## 支线剧情\n{_format_sub_plot(threads)}",
        })
    # 6. character_card 人物 (s1.4 新增)
    characters = character_card.get('characters', []) if isinstance(character_card, dict) else []
    if characters:
        messages.append({
            "role": "user",
            "content": f"## 人物\n{_format_characters(characters)}",
        })
    # 7. seed_table 种子 (s1.4 新增)
    seeds = seed_table.get('seeds', []) if isinstance(seed_table, dict) else []
    if seeds:
        messages.append({
            "role": "user",
            "content": f"## 种子\n{_format_seeds(seeds)}",
        })
    # 8. chapter_summaries 分级结构
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


# ============ v0.8.2: Onboard 阶段 messages 拼装 ============


def build_messages_for_onboarding_step3(
        project_id: str,
        current_user_message: str,
        system_prompt: str,
) -> List[Dict[str, Any]]:
    """v0.8.2 故事引擎 Agent (Step 3) 的 messages

    与 reading 阶段不同: 不需要 7 件全件 (Step 3 还没完成),
    只拼: world_tree + style_charter + genre_resonance (Step 1 已有)
         + Step 1-2 已有数据 (genres/styles/tone/palette)

    结构:
    1. system: ONBOARDING_STEP3_PROMPT (v0.7 prompt 模板)
    2. data:   Step 1-2 已有 payload
    3. history: 用户与管家之前的对话
    4. current: user message
    """
    from realtime_novel.persistence.project_repository import ProjectRepository
    from realtime_novel.persistence.sqlite_store import get_store

    messages = []
    # 1. system
    messages.append({"role": "system", "content": system_prompt})

    # 2. data: 读 onboarding_state + 7 件 (Step 1 写过的 world_tree/style_charter/genre_resonance)
    try:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT state_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row:
            state = json.loads(row["state_json"]) if hasattr(json, 'loads') else {}
            payload = state.get("payload", {})
            # 读 7 件 (Step 1 已写)
            data = _load_project_data(project_id)
            wt = data.get("01-world-tree.yaml", {}) or {}
            sc = data.get("02-style-charter.yaml", {}) or {}
            gr = data.get("03-genre-resonance.yaml", {}) or {}
            data_block = f"""## Step 1-2 已有数据
- 题材: {payload.get("genres", [])}
- 风格: {payload.get("styles", [])}
- 基调: {payload.get("tone", [])}
- 调色板: {payload.get("palette", "")}

## 世界树
{_format_world_tree_compact(wt)}

## 风格宪法 (v0.8.2 推断完整)
{_format_style_charter(sc)}

## 题材共鸣
{chr(10).join([f"+ {a.get('text', a) if isinstance(a, dict) else a}" for a in gr.get("accept", [])]) or "（无）'"}
"""
            messages.append({"role": "system", "content": data_block})
    except Exception:
        pass  # 推断失败不阻断 onboarding

    # 3. history (Step 3 是多轮对话, 拿最近 3 轮)
    history = _load_project_history(project_id, max_history=3)
    messages.extend(history)

    # 4. current
    messages.append({"role": "user", "content": current_user_message or "请提议 3 个故事引擎字段"})
    return messages


def build_messages_for_onboarding_step4(
        project_id: str,
        current_user_message: str,
        system_prompt: str,
) -> List[Dict[str, Any]]:
    """故事路径 Agent (Step 4) 的 messages

    与 Step 3 不同: 此时 Step 3 已确认, 需要拼:
    - Step 1-2 已有数据
    - Step 3 已写入的 7 件 (style_charter / main_plot / character_card)
    - Step 4 当前 user 输入

    结构同 Step 3 但 max_history 更大 (Step 4 在 Step 3 之后, 历史更长)
    """
    return build_messages_for_onboarding_step3(
        project_id=project_id,
        current_user_message=current_user_message,
        system_prompt=system_prompt,
    )


def _load_project_history(project_id: str, max_history: int = 5) -> list[dict[str, Any] | None]:
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
