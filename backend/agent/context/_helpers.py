"""context._helpers — 私有 helper（DB 转换 + 字段格式化 + json_dumps）

v0.6.1 P4: 从 context_builder.py 拆出

公开:
- load_history_messages: 取历史 N 条转 OpenAI 格式

私有:
- _row_to_message: DB message row → OpenAI 格式
- _load_project_data: 加载项目 7 件基座 + 章节 metadata
- _format_*: 7 件字段格式化 (chapter_summaries/world_tree/main_plot/sub_plot/characters/seeds)
- json_dumps: 中文安全 JSON 序列化
"""
from __future__ import annotations

import json
from typing import List, Dict, Any, Optional

from backend.persistence import (
    ProjectRepository, ChapterRepository,
    ConversationRepository,
)


# ============ v0.4.1 基础 ============

def _row_to_message(row: dict) -> Optional[Dict[str, Any]]:
    """DB message row → OpenAI 格式 message

    冷启动 rebuild 场景只保留纯对话消息（user / assistant 无 tool_calls）：
    - role=tool → 返回 None（历史 tool 消息缺少 tool_call_id，无法还原合法链路）
    - role=assistant + tool_calls → 返回 None（孤立的 assistant tool_calls 消息
      无对应 tool message，会让 LLM 误以为工具还未执行）
    - role=user / role=assistant（纯文本）→ 正常返回
    """
    role = row.get("role")
    content = row.get("content") or ""

    if role == "tool":
        # tool 消息无法安全还原（缺 tool_call_id），冷启动时丢弃
        return None

    if role == "assistant":
        tool_calls = row.get("tool_calls")
        if tool_calls:
            # 带 tool_calls 的 assistant 消息若无对应 tool message 会破坏上下文
            # 冷启动时一并丢弃
            return None
        return {"role": "assistant", "content": content}

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
    """加载项目所有 7 件基座 + 章节 metadata + volumes

    v004 增强：加 list_volumes
    背景：之前漏了 list_volumes 导致 _format_chapter_summaries_by_volume
         拿到的是空 list，所有章节都进 "__no_volume__" 分组 = 无卷模式

    Returns:
        {
            "world_tree": {...},
            "style_pack_id": "...",
            "genre_resonance": {...},
            "main_plot": {...},
            "sub_plot": {...},
            "character_card": {...},
            "seed_table": {...},
            "chapters": [ChapterRow, ...],
            "volumes": [VolumeRow, ...],     # v004 新增
        }
    """
    proj_repo = ProjectRepository()
    chap_repo = ChapterRepository()

    artifacts = proj_repo.load_all_artifacts(project_id)
    chapters = chap_repo.list_by_project(project_id, limit=200)
    volumes = proj_repo.list_volumes(project_id)  # v004 新增
    return {**artifacts, "chapters": chapters, "volumes": volumes}


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
    """压缩 world_tree 为字符串（架构师/文笔家用）

    v003 重构（spec §5.4）：
    - timeline / geography 等已拆表的数据由调用方通过 repo.list_timeline_events / list_geography_locations 单独注入
    - 本函数仅承担 world_tree 5 字段（story_core / genre_tags / core_rules）的格式化
    """
    if not world_tree:
        return "（世界树为空）"

    parts = []

    story_core = world_tree.get("story_core")
    if story_core:
        parts.append(f"故事核心: {story_core}")

    genre_tags = world_tree.get("genre_tags", [])
    if genre_tags:
        parts.append(f"题材: {', '.join(genre_tags)}")

    core_rules = world_tree.get("core_rules", []) or []
    if core_rules:
        rules_str = "; ".join([f"{r.get('id', '')}: {r.get('statement', '')}" for r in core_rules])
        parts.append(f"硬约束清单: {rules_str}")

    return "\n".join(parts) if parts else "（世界树无核心信息）"


# s1.4 新增: 5 个 helper 格式化 7 件基座其余字段


def _format_world_tree_baseline(
    world_tree: Optional[Dict[str, Any]],
    world_entries: List[Any],
    timeline_events: List[Any],
    geography_locations: List[Any],
    max_world_entries: int = 20,
    max_timeline_events: int = 10,
    max_geography_locations: int = 10,
) -> str:
    """世界树基座完整上下文（spec §5.4 注入顺序）

    顺序：
    1. core_rules（硬约束清单）
    2. world_entries（知识库）
    3. timeline_events（时间线）
    4. geography_locations（地理场景）
    5. world_tree.story_core / genre_tags

    v003 新增
    """
    parts = []

    # 1. core_rules 硬约束
    core_rules = (world_tree or {}).get("core_rules", []) or []
    if core_rules:
        rules_str = "; ".join([f"{r.get('id', '')}: {r.get('statement', '')}" for r in core_rules])
        parts.append(f"硬约束清单: {rules_str}")

    # 2. world_entries 知识库
    if world_entries:
        we_str = "; ".join([
            f"[{e.category}] {e.title}: {(e.content or '')[:80]}"
            for e in world_entries[:max_world_entries]
        ])
        parts.append(f"知识库: {we_str}")

    # 3. timeline_events 时间线
    if timeline_events:
        te_str = "; ".join([
            f"[{e.era_name or ''}] {e.event_name or ''}"
            for e in timeline_events[:max_timeline_events]
        ])
        parts.append(f"时间线: {te_str}")

    # 4. geography_locations 地理场景
    if geography_locations:
        gl_str = "; ".join([
            f"[{l.category}] {l.name}"
            for l in geography_locations[:max_geography_locations]
        ])
        parts.append(f"地理场景: {gl_str}")

    # 5. story_core + genre_tags
    if world_tree:
        if world_tree.get("story_core"):
            parts.append(f"故事核心: {world_tree['story_core']}")
        if world_tree.get("genre_tags"):
            parts.append(f"题材: {', '.join(world_tree['genre_tags'])}")

    return "\n".join(parts) if parts else "（世界树为空）"


def _format_main_plot(main_plot: dict) -> str:
    """压缩 main_plot 为字符串（文笔家用）

    包含：
    - arc_phrase：Step 3 story_core 故事内核
    - beats：Step 4 main_arc 拆出的节奏节点
    - metadata.story_core / main_arc：完整文字（不只靠 arc_phrase + beats）
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

    metadata = main_plot.get('metadata') or {}
    if isinstance(metadata, dict):
        for key, label in [('story_core', '故事内核'), ('main_arc', '主线节点')]:
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
    v007: 加入 trigger / payoff 显示
    """
    if not seeds:
        return "（种子为空）"
    lines = []
    for s in seeds[:20]:
        name = s.get('name', '') or ''
        content = s.get('content', '')
        trigger = s.get('trigger', '') or ''
        payoff = s.get('payoff', '') or ''
        estimated = s.get('estimated_chapter')
        payoff_ch = s.get('payoff_chapter')
        status = s.get('status', '')

        label = name if name else content[:40]
        line = f"- [{label}]"
        if trigger:
            line += f" 触发: {trigger[:60]}"
        if payoff:
            line += f" 回收: {payoff[:60]}"
        ch_parts = []
        if estimated:
            ch_parts.append(f"预规ch{estimated}")
        if payoff_ch:
            ch_parts.append(f"回收ch{payoff_ch}")
        if ch_parts:
            line += f" ({', '.join(ch_parts)})"
        if status and status != 'planted':
            line += f" [{status}]"
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


async def load_chat_history(
    user_id: str,
    session_rounds: int = 15,
) -> List[Dict[str, Any]]:
    """管家 CHAT 路径 history 加载（cache miss 时的冷启动 rebuild）

    设计：
    - 只读当前 active conv 的最近 session_rounds 条消息
    - 只保留纯对话消息（user / assistant 无 tool_calls），过滤掉 tool 消息
      和带 tool_calls 的 assistant 消息——这类消息在 DB 中缺失 tool_call_id
      等关键字段，无法安全还原为合法的 OpenAI 工具链，贸然注入会让 LLM
      误判上下文状态。
    - 去掉最后一条 user 消息：ws_manager 在调 steward.receive() 前已把本次
      user_message 存入 DB，executor 末尾会自己 append，不能重复

    背景：
    - cache hit 路径完全不走本函数（NovelSteward.receive 中已短路）
    - cache miss 只发生在进程重启 / TTL 超时（24h）
    - 此时只需恢复当前 active session 的近期上下文，不需要跨 conv 的历史基底：
      TTL 超时意味着新的一天，invalidated conv 的内容是噪音；
      进程重启时 active conv 的近 15 条已足够恢复上下文。

    Returns:
        list[dict]: OpenAI 格式 messages（仅含纯 user/assistant 对话消息）
    """
    from backend.persistence.conversation_repository import ConversationRepository

    conv_repo = ConversationRepository()
    result: List[Dict[str, Any]] = []

    try:
        active = await conv_repo.get_active_conversation(user_id)
        if active:
            session_msgs = await conv_repo.get_messages(active.id, limit=session_rounds)
            # DESC → ASC 翻转
            session_msgs = list(reversed(session_msgs))
            # 去掉最后一条 user 消息（本次请求的消息，executor 会自己 append）
            if session_msgs and (
                session_msgs[-1].role.value
                if hasattr(session_msgs[-1].role, "value")
                else session_msgs[-1].role
            ) == "user":
                session_msgs = session_msgs[:-1]
            for m in session_msgs:
                d = {
                    "id": m.id,
                    "role": m.role.value if hasattr(m.role, "value") else m.role,
                    "content": m.content,
                    "tool_calls": m.tool_calls,
                    "tool_results": m.tool_results,
                }
                msg = _row_to_message(d)
                if msg:
                    result.append(msg)
    except Exception as e:
        import logging
        logging.warning(f"load_chat_history: session 加载失败: {e}", exc_info=True)

    return result


# v0.9.4 新增：detailed_summary 字段已删 → 改用「历史卷维度 description」+「当前卷下所有章节 summary」
# v004 增强（欧尼酱 20:16）：用 volumes.status 区分完结/进行中，完结卷优先用 volume.summary
def _format_chapter_summaries_by_volume(chapters: list, volumes: list) -> str:
    """按卷维度组织章节摘要

    v004 设计：
    - 当前卷 = status=in_progress 的卷中 volume_num 最大的卷
      （如果有多个进行中卷，取 volume_num 最大；优先用 volumes 表而不是章节推断）
    - 完结卷（status=completed）优先输出 volume.summary（1000 字总结）
    - 进行中卷列出所有章节 summary
    - 无 volume_id 归属的章节归到"未分配"段

    节省 token 的同时保留关键信息：
    - 完结卷 1 段 1000 字总结（VolumeRow.summary）
    - 进行中卷所有章节 1 句 summary
    """
    if not chapters and not volumes:
        return "（暂无章节）"

    # 1. 找当前进行中卷 = status=in_progress 中 volume_num 最大的
    in_progress_volumes = [
        v for v in (volumes or [])
        if str(getattr(v, "status", "")) == "in_progress"
    ]
    current_volume_id = None
    if in_progress_volumes:
        # 按 volume_num 降序，取第一个
        current_volume = max(in_progress_volumes, key=lambda v: v.volume_num)
        current_volume_id = current_volume.id
    # else: 没有 in_progress 卷 → current_volume_id 保持 None
    #     （所有卷都完结的场景，不该有"当前卷"）
    #     （之前 fallback 取最新章节 volume_id 是错的，
    #       会让一个 completed 的卷被误标为"当前卷 进行中"）

    # 2. volume_id → VolumeRow 映射
    vol_map: Dict[str, Any] = {v.id: v for v in (volumes or []) if getattr(v, "id", None)}

    # 3. 按 volume_id 分组章节
    by_volume: Dict[str, list] = {}
    unassigned: list = []
    for ch in chapters:
        vid = getattr(ch, "volume_id", None)
        if vid:
            by_volume.setdefault(vid, []).append(ch)
        else:
            unassigned.append(ch)

    # 4. 按 volume_num 升序输出
    sorted_volume_ids = sorted(
        by_volume.keys(),
        key=lambda v: (vol_map[v].volume_num if v in vol_map else 9999, v),
    )

    lines = []
    for vid in sorted_volume_ids:
        vol_chapters = sorted(by_volume[vid], key=lambda c: c.chapter_num)
        vol = vol_map.get(vid)
        is_current = (vid == current_volume_id)
        is_completed = (vol is not None and str(getattr(vol, "status", "")) == "completed")
        vol_summary = getattr(vol, "summary", None) if vol else None

        if is_current:
            # 当前卷（进行中）：列出所有章节
            if vol:
                lines.append(f"【当前卷 {vol.volume_num}：{vol.title}】（进行中）")
            else:
                lines.append("【当前卷】")
            if vol_summary:
                # 有总结先输出（即使进行中）
                lines.append(f"  总结: {vol_summary}")
            for ch in vol_chapters:
                if getattr(ch, "summary", None):
                    title = getattr(ch, "title", "") or ""
                    if title:
                        lines.append(f"  - 第{ch.chapter_num}章 {title}: {ch.summary}".rstrip())
                    else:
                        lines.append(f"  - 第{ch.chapter_num}章: {ch.summary}".rstrip())
        elif is_completed:
            # 完结卷：只保留 vol.summary，不列章节（v0.9.6 拍板：欧尼酱 21:24）
            # 设计：vol.summary (1000字) 已足够描述整卷全部内容
            #       章节 detail 在 vol.summary 里都已涵盖，不需要再列
            if vol:
                lines.append(f"【历史卷 {vol.volume_num}：{vol.title}】（已完结）")
                if vol_summary:
                    lines.append(f"  总结: {vol_summary}")
                else:
                    # fallback：没 vol_summary 时用 description + 章节列表
                    vol_desc = getattr(vol, "description", "") or ""
                    if vol_desc:
                        lines.append(f"  {vol_desc}")
                    for ch in vol_chapters:
                        if getattr(ch, "summary", None):
                            title = getattr(ch, "title", "") or ""
                            if title:
                                lines.append(f"  - 第{ch.chapter_num}章 {title}: {ch.summary}".rstrip())
                            else:
                                lines.append(f"  - 第{ch.chapter_num}章: {ch.summary}")
            else:
                lines.append("【历史卷】")
            lines.append("")
        else:
            # 未识别为当前/完结的（异常情况）
            if vol:
                vol_desc = getattr(vol, "description", "") or ""
                lines.append(f"【历史卷 {vol.volume_num}：{vol.title}】{vol_desc}")
            else:
                lines.append("【历史卷】")
            for ch in vol_chapters:
                if getattr(ch, "summary", None):
                    lines.append(f"  - 第{ch.chapter_num}章: {ch.summary}")
            lines.append("")

    # 5. 未分配章节
    if unassigned:
        lines.append("【未分配卷的章节】")
        for ch in sorted(unassigned, key=lambda c: c.chapter_num):
            if getattr(ch, "summary", None):
                title = getattr(ch, "title", "") or ""
                if title:
                    lines.append(f"  - 第{ch.chapter_num}章 {title}: {ch.summary}".rstrip())
                else:
                    lines.append(f"  - 第{ch.chapter_num}章: {ch.summary}".rstrip())

    return "\n".join(lines) if lines else "（暂无章节）"
