"""context._helpers — 私有 helper（DB 转换 + 字段格式化 + json_dumps）

v0.6.1 P4: 从 context_builder.py 拆出

公开:
- load_history_messages: 取历史 N 条转 OpenAI 格式

私有:
- _row_to_message: DB message row → OpenAI 格式
- _load_project_data: 加载项目 7 件基座 + 章节 metadata
- _format_*: 7 件字段格式化 (chapter_summaries/world_tree/style_charter/main_plot/sub_plot/characters/seeds)
- json_dumps: 中文安全 JSON 序列化
"""
from __future__ import annotations

import json
from typing import List, Dict, Any, Optional

from backend.persistence import (
    ProjectRepository, ChapterRepository,
    ConversationRepository, OnboardingRepository,
)


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
    """从 ConversationRepository 取历史 N 条（按 created_at 升序），转 OpenAI 格式"""
    import asyncio
    import concurrent.futures

    repo = ConversationRepository()

    async def _fetch():
        return await repo.get_messages(conversation_id, limit=max_history)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as ex:
                rows = ex.submit(asyncio.run, _fetch()).result()
        else:
            rows = asyncio.run(_fetch())
    except RuntimeError:
        rows = asyncio.run(_fetch())

    # get_messages 返回 DESC，需要翻转为 ASC
    rows = list(rows)[::-1]
    messages = []
    for msg_obj in rows:
        if exclude_message_id and msg_obj.id == exclude_message_id:
            continue
        # 将 Message dataclass 转为 dict 供 _row_to_message 使用
        d = {
            "id": msg_obj.id,
            "role": msg_obj.role.value if hasattr(msg_obj.role, 'value') else msg_obj.role,
            "content": msg_obj.content,
            "tool_calls": msg_obj.tool_calls,
            "tool_results": msg_obj.tool_results,
        }
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

    包含:
    - arc_phrase (Step 3 story_core 故事一句话)
    - beats (Step 4 main_arc 拆的节奏)
    - metadata.story_core / main_arc / reader_feeling
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

    # v0.8.3: metadata 里保存了 Step 3 story_core / Step 4 main_arc / reader_feeling
    # 给 LLM 看到全量信息 (不能只靠 arc_phrase + beats)
    metadata = main_plot.get('metadata') or {}
    if isinstance(metadata, dict):
        for key, label in [('story_core', '故事内核'), ('main_arc', '主线节点'), ('reader_feeling', '读者情绪')]:
            v = metadata.get(key, '')
            if v and v not in (main_plot.get('arc_phrase', '') or ''):
                parts.append(f"{label}: {v}")

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




def json_dumps(obj: Any) -> str:
    """安全的 JSON dump"""
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)




def _load_project_history(project_id: str, max_history: int = 5) -> list[dict[str, Any] | None]:
    """按 project_id 取历史（per-project 维度），经 ConversationRepository 查询

    v0.6.1: 从 onboarding_builders.py 移到 _helpers.py (通用能力)
    - 之前在 onboarding_builders 内部用, 但 build_messages_for_chapter_generator
      (在 builders.py) 也调它, 引发 NameError
    - 修法: 移到通用 helper, onboarding_builders 改为 import
    """
    import asyncio
    import concurrent.futures

    repo = ConversationRepository()

    async def _fetch():
        return await repo.get_messages_by_project(project_id, limit=max_history)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as ex:
                msg_list = ex.submit(asyncio.run, _fetch()).result()
        else:
            msg_list = asyncio.run(_fetch())
    except RuntimeError:
        msg_list = asyncio.run(_fetch())

    # get_messages_by_project 返回 DESC，翻转为 ASC
    msg_list = [m for m in reversed(msg_list)
                if m.role.value in ('user', 'assistant')]
    result = []
    for msg_obj in msg_list:
        d = {
            "id": msg_obj.id,
            "role": msg_obj.role.value if hasattr(msg_obj.role, 'value') else msg_obj.role,
            "content": msg_obj.content,
            "tool_calls": msg_obj.tool_calls,
            "tool_results": msg_obj.tool_results,
        }
        m = _row_to_message(d)
        if m:
            result.append(m)
    return result
