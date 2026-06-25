"""context.builders — 3 角色 messages 拼装 + node 通用 builder

v0.6.1 P4: 从 context_builder.py 拆出

- build_messages_for_steward: 管家 (user 维度, 不绑 project)
- build_messages_for_worldtree_keeper: 架构师 (per-project)
- build_messages_for_chapter_generator: 文笔家 (per-project, chapter_summaries 分级)
- build_messages_for_node: 通用 (v0.4 6 节点 StateGraph 时期遗留, intake/respond 用)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.agent.context._helpers import (
    load_history_messages,
    _load_project_data,
    _load_project_history,
    _format_chapter_summaries_short,
    _format_chapter_summaries_graded,
    _format_world_tree_compact,
    _format_style_charter,
    _format_main_plot,
    _format_sub_plot,
    _format_characters,
    _format_seeds,
)


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
    from backend.persistence import ConversationRepository
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
        # 3. summary（先查，插在 history 之前）
        async def _get_conv():
            return await ConversationRepository().get_conversation(conv_id)

        try:
            loop2 = asyncio.get_event_loop()
            if loop2.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as ex:
                    conv_obj = ex.submit(asyncio.run, _get_conv()).result()
            else:
                conv_obj = asyncio.run(_get_conv())
        except RuntimeError:
            conv_obj = asyncio.run(_get_conv())

        history = load_history_messages(conv_id, max_history=max_history)
        # 2. history
        messages.extend(history)
        # 3. summary（如果有）
        if conv_obj and conv_obj.summary:
            messages.insert(1, {
                "role": "system",
                "content": f"历史对话摘要: {conv_obj.summary}",
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
    world_tree = data.get("world_tree", {})
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
    world_tree = data.get("world_tree", {})
    style_charter = data.get("style_charter", {})
    main_plot_raw = data.get("main_plot", {})
    sub_plot_raw = data.get("sub_plot", {})
    character_card = data.get("character_card", {})
    seed_table = data.get("seed_table", {})
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
