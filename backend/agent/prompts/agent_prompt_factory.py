"""agent_prompt_factory — Agent system_prompt 组装工厂

接管文笔家（novel_writer）和架构师（world_tree_manager）的完整 system_prompt 主体组装。

组装内容（按顺序）：
1. 【身份】— agent 身份/职责/工作流骨架
2. 【写作笔风】— 从 style_pack 库查出的完整笔风框架
3. 【写作法则】— 全局必备 + 本笔风定向关联
4. 【绝对禁止】— 8 条红线
5. 【项目基座定调】— world_tree + genre_resonance 摘要（定调用，完整 7 件走 context）

不负责拼接的内容（由 executor 的 _build_system_prompt 统一处理）：
- 工具清单（动态，含 extra_tools）
- ReAct 输出格式 + 约束
- project_id / context dict

另外提供：
- build_project_context_message(): 7 件基座完整数据 + 章节摘要 → 独立 user message
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.agent.context._helpers import (
    _load_project_data,
    _format_world_tree_compact,
    _format_chapter_summaries_graded,
    _format_chapter_summaries_short,
    _format_main_plot,
    _format_sub_plot,
    _format_characters,
    _format_seeds,
)
from backend.agent.prompts.style_packs import get_style_pack_or_default
from backend.agent.prompts.writing_laws import get_laws_for_style, get_red_lines

_logger = logging.getLogger(__name__)


# ============ 身份骨架 ============

_WRITER_IDENTITY = """你是「小说文笔家」。

【职责】
在 7 件基座（world_tree / style_pack / genre_resonance / main_plot / sub_plots / character_card / seed_table）的约束下，生成下一章小说正文，并通过工具落盘。

【工作流】
1. system_prompt 已注入笔风、写作法则、基座定调；context 已注入完整 7 件基座 + chapter_summaries
2. 如有需要（如用户明确要求查某章详情），可调 read_chapter 检索上下文
3. 写正文（3000-4500 字，严格遵守下方笔风和法则）
4. 调 generate_chapter(content=正文, project_id=xxx, intervention=?, actor_feedback=?, actor_character=?) 落盘
5. 调 summarize_chapter(content=正文, project_id=xxx) 抽 1 句话 summary（自动写入 DB）
6. final_response 是「已落盘第 N 章《XXX》, 摘要: ...」（不要把全文塞进 final_response）

【输出格式】
- 章节正文直接是小说文字（markdown 格式，包含 # 第 N 章标题）
- 章节正文里不要嵌入 ###SUMMARY### 块（summary 由 summarize_chapter 工具抽取）
- final_response 是一句话总结：「已落盘第 N 章《XXX》（X 字），摘要：...」

【关键约束】
- 严格遵守 7 件基座 + 下方笔风法则
- 修改基座前不要直接调 edit_artifact/update_base —— 这是架构师（world_tree_manager）职责，文笔家只读
- 不决定剧情走向（走向由世界树管理维护）
- 章节字数硬约束：3000-4500 字

【上下文获取策略】
- 默认相信 system_prompt + context 注入的基座和摘要，不要重复调 load_project
- 只在以下情况调 read_chapter：用户明确说「重读第 N 章」「参考第 N 章的风格」
"""

_WORLDTREE_IDENTITY = """你是「世界树管理」。

【职责】
当用户对项目内的世界树基座进行干预时，你负责分析影响范围、调整基座、保持一致性。

【可用基座 7 件】
1. world_tree - 时间线、地理、核心规则
2. style_pack - 写作笔风（第 7 件基座）
3. genre_resonance - 题材、情绪基调
4. main_plot - 主线弧线
5. sub_plots - 支线
6. character_card - 角色卡
7. seed_table - 伏笔种子

【典型工作流】
1. 调用 load_project 获取当前 7 件基座（如 context 未预注入）
2. 分析用户干预的影响：
   - 涉及哪些基座的哪些字段？
   - 是否影响主线弧线（main_plot）？
   - 是否需要埋伏笔（seed_table）？
   - 是否引发 7 件之间的矛盾？
4. 调用对应 tool 执行修改：
   - 简单字段改 → update_base
   - 复杂结构改 → edit_artifact
   - 主线/支线调整 → weave_plot
   - 角色状态变化 → introspect_character
5. 输出 final_response，必须是 JSON 格式的 WorldTreeDiff

【关键约束】
- 修改基座前必须先 load_project 看清现状（或查看 context 预注入的基座）
- 不能让 7 件基座内部矛盾（如改完 character_card 让 world_tree 冲突）
- 长程伏笔（seed_table）必须明确 trigger + payoff + estimated_chapter
- 多个改动可并行调用 tool
- 最终 JSON 必须是合法 JSON，不要包含 markdown 包裹

【一致性原则】
- world_tree 与 character_card 不能矛盾（如世界规则说「无魔法」，角色不能会魔法）
- main_plot 与 sub_plots 不能矛盾
- seed_table 的 payoff 不能超出 main_plot 范围
"""


# ============ 内部格式化函数 ============

def _get_project_style_pack_id(project_id: str) -> Optional[str]:
    """从 projects 表读 style_pack_id

    容错：字段不存在或值为空时返回 None（调用方用默认笔风）。
    后续 DB 迁移加字段后自然生效。
    """
    try:
        from backend.persistence.sqlite_store import get_store
        with get_store().connection() as conn:
            try:
                row = conn.execute(
                    "SELECT style_pack_id FROM projects WHERE id = ?",
                    (project_id,),
                ).fetchone()
                if row:
                    return row[0] or None
            except Exception:
                # 字段不存在，静默降级
                return None
    except Exception as e:
        _logger.debug("_get_project_style_pack_id: 读取失败 project_id=%s: %s", project_id, e)
    return None


def _format_style_pack(pack: Dict[str, Any]) -> str:
    """格式化笔风为 prompt 文本"""
    parts: List[str] = []
    parts.append(f"笔风：{pack['name']}（{pack['tagline']}）")
    parts.append("")

    ci = pack.get("core_idea", {})
    if ci:
        parts.append("【核心理念】")
        if ci.get("shell"):
            parts.append(f"  外壳：{ci['shell']}")
        if ci.get("core"):
            parts.append(f"  内核：{ci['core']}")
        if ci.get("soul"):
            parts.append(f"  灵魂：{ci['soul']}")
        parts.append("")

    if pack.get("tone"):
        parts.append(f"【故事基调】{pack['tone']}")
        parts.append("")

    wt = pack.get("worldview_texture", [])
    if wt:
        parts.append("【世界观质感】")
        for line in wt:
            parts.append(f"  - {line}")
        parts.append("")

    narr = pack.get("narrative", {})
    if narr:
        parts.append("【叙事笔法】")
        if narr.get("focus"):
            parts.append("  聚焦：")
            for f in narr["focus"]:
                parts.append(f"    - {f}")
        if narr.get("rhetoric"):
            parts.append("  修辞：")
            for r in narr["rhetoric"]:
                parts.append(f"    - {r}")
        if narr.get("dialogue"):
            parts.append("  对话：")
            for d in narr["dialogue"]:
                parts.append(f"    - {d}")
        if narr.get("rhythm"):
            parts.append(f"  节奏：{narr['rhythm']}")
        parts.append("")

    img = pack.get("imagery", {})
    if img:
        parts.append("【意象库】")
        if img.get("scenes"):
            parts.append(f"  场景：{', '.join(img['scenes'])}")
        if img.get("props"):
            parts.append(f"  道具：{', '.join(img['props'])}")
        if img.get("colors"):
            parts.append(f"  色彩：{', '.join(img['colors'])}")
        parts.append("")

    prin = pack.get("principles", {})
    if prin:
        if prin.get("believe"):
            parts.append("【笔风信念】")
            for b in prin["believe"]:
                parts.append(f"  - {b}")
            parts.append("")
        if prin.get("avoid"):
            parts.append("【笔风禁区】")
            for a in prin["avoid"]:
                parts.append(f"  - {a}")
            parts.append("")
        if prin.get("achieve"):
            parts.append("【笔风目标】")
            for a in prin["achieve"]:
                parts.append(f"  - {a}")
            parts.append("")

    samples = pack.get("samples", [])
    if samples:
        parts.append("【灵魂样本】（以下是这种笔风的标杆片段，模仿其质感和节奏）")
        for i, s in enumerate(samples, 1):
            parts.append(f"  样本{i}：")
            parts.append(f"  {s}")
            parts.append("")

    return "\n".join(parts)


def _format_laws(laws: List[Dict[str, Any]]) -> str:
    """格式化法则为 prompt 文本"""
    parts: List[str] = []
    for law in laws:
        parts.append(f"■ {law['name']}")
        for rule in law.get("rules", []):
            parts.append(f"  ✓ {rule}")
        for avoid in law.get("avoid_list", []):
            parts.append(f"  ✗ {avoid}")
        parts.append("")
    return "\n".join(parts)


def _format_red_lines(red_lines: List[Dict[str, Any]]) -> str:
    """格式化红线为 prompt 文本"""
    parts: List[str] = []
    for rl in red_lines:
        parts.append(f"  {rl['id']}. {rl['title']}")
        parts.append(f"     {rl['desc']}")
    return "\n".join(parts)


def _format_base_summary(project_data: Dict[str, Any]) -> str:
    """格式化基座摘要（world_tree + genre_resonance），定调用

    完整 7 件走 context message，这里只放精简定调信息。
    """
    parts: List[str] = []

    # world_tree 摘要
    wt = project_data.get("world_tree", {})
    wt_str = _format_world_tree_compact(wt)
    parts.append("【世界树定调】")
    parts.append(wt_str)
    parts.append("")

    # genre_resonance 摘要
    gr = project_data.get("genre_resonance", {})
    if gr:
        parts.append("【题材共振】")
        accept = gr.get("accept", [])
        reject = gr.get("reject", [])
        anchors = gr.get("anchors", [])
        if accept:
            parts.append(f"  接纳：{', '.join(str(a) for a in accept[:5])}")
        if reject:
            parts.append(f"  拒绝：{', '.join(str(r) for r in reject[:5])}")
        if anchors:
            parts.append(f"  锚点：{', '.join(str(a) for a in anchors[:5])}")
        parts.append("")

    return "\n".join(parts)


# ============ 公开 API ============

def build_writer_system_prompt(project_id: str) -> str:
    """组装文笔家 system_prompt 主体

    组装内容：身份 + 笔风 + 法则 + 红线 + 基座定调
    （工具清单 + ReAct 格式由 executor 追加）

    Args:
        project_id: 项目 ID

    Returns:
        完整的 system_prompt 主体文本
    """
    # 1. 读项目的 style_pack_id
    pack_id = _get_project_style_pack_id(project_id)
    pack = get_style_pack_or_default(pack_id)

    # 2. 查法则（全局必备 + 定向关联）
    effective_pack_id = pack["id"]
    laws = get_laws_for_style(effective_pack_id)
    red_lines = get_red_lines()

    # 3. 加载基座数据（用于摘要）
    try:
        project_data = _load_project_data(project_id)
    except Exception as e:
        _logger.warning("build_writer_system_prompt: 加载基座失败 project_id=%s: %s", project_id, e)
        project_data = {}

    # 4. 拼装
    parts: List[str] = []
    parts.append(_WRITER_IDENTITY)
    parts.append("=" * 60)
    parts.append("")
    parts.append(_format_style_pack(pack))
    parts.append("=" * 60)
    parts.append("")
    parts.append("【写作法则 — 全局必备 + 本笔风强化】")
    parts.append("以下法则必须逐条遵守，✓ 是必须做到的，✗ 是必须避免的：")
    parts.append("")
    parts.append(_format_laws(laws))
    parts.append("=" * 60)
    parts.append("")
    parts.append("【绝对禁止（红线）】")
    parts.append("以下 8 条是终极硬性禁令，任何情况下都不得违反：")
    parts.append("")
    parts.append(_format_red_lines(red_lines))
    parts.append("")
    parts.append("=" * 60)
    parts.append("")
    base_summary = _format_base_summary(project_data)
    if base_summary.strip():
        parts.append("【项目基座定调】")
        parts.append("（完整 7 件基座已注入 context 上下文，以下是精简定调）")
        parts.append("")
        parts.append(base_summary)

    return "\n".join(parts)


def build_worldtree_system_prompt(project_id: str) -> str:
    """组装架构师 system_prompt 主体

    组装内容：身份 + 笔风 + 法则 + 红线 + 基座定调
    （工具清单 + ReAct 格式由 executor 追加）

    Args:
        project_id: 项目 ID

    Returns:
        完整的 system_prompt 主体文本
    """
    # 1. 读项目的 style_pack_id
    pack_id = _get_project_style_pack_id(project_id)
    pack = get_style_pack_or_default(pack_id)

    # 2. 查法则（全局必备 + 定向关联）
    effective_pack_id = pack["id"]
    laws = get_laws_for_style(effective_pack_id)
    red_lines = get_red_lines()

    # 3. 加载基座数据（用于摘要）
    try:
        project_data = _load_project_data(project_id)
    except Exception as e:
        _logger.warning("build_worldtree_system_prompt: 加载基座失败 project_id=%s: %s", project_id, e)
        project_data = {}

    # 4. 拼装
    parts: List[str] = []
    parts.append(_WORLDTREE_IDENTITY)
    parts.append("=" * 60)
    parts.append("")
    parts.append("【当前项目笔风】（调整基座时需保持笔风一致性）")
    parts.append(f"笔风：{pack['name']}（{pack['tagline']}）")
    ci = pack.get("core_idea", {})
    if ci.get("core"):
        parts.append(f"  内核：{ci['core']}")
    if ci.get("soul"):
        parts.append(f"  灵魂：{ci['soul']}")
    parts.append("")
    parts.append("=" * 60)
    parts.append("")
    parts.append("【写作法则 — 调整基座时需兼顾】")
    parts.append("以下法则约束文笔家的写作，你在调整基座时需确保不与这些法则冲突：")
    parts.append("")
    parts.append(_format_laws(laws))
    parts.append("=" * 60)
    parts.append("")
    parts.append("【绝对禁止（红线）】")
    parts.append("调整基座时不得引入以下问题：")
    parts.append("")
    parts.append(_format_red_lines(red_lines))
    parts.append("")
    parts.append("=" * 60)
    parts.append("")
    base_summary = _format_base_summary(project_data)
    if base_summary.strip():
        parts.append("【项目基座定调】")
        parts.append("（完整 7 件基座已注入 context 上下文，以下是精简定调）")
        parts.append("")
        parts.append(base_summary)

    return "\n".join(parts)


def build_project_context_message(project_id: str, agent_name: str) -> str:
    """组装项目上下文 message（7 件基座完整数据 + 章节摘要）

    作为独立 user message 注入 messages 列表，不进 system_prompt。
    完整 7 件基座 + 章节摘要（分级/简短，按 agent 类型选）。

    Args:
        project_id: 项目 ID
        agent_name: agent 名称（novel_writer 用分级摘要，world_tree_manager 用简短摘要）

    Returns:
        context message 文本
    """
    try:
        project_data = _load_project_data(project_id)
    except Exception as e:
        _logger.warning(
            "build_project_context_message: 加载失败 project_id=%s: %s",
            project_id, e,
        )
        return f"【项目上下文】\n（基座加载失败: {e}）"

    chapters = project_data.get("chapters", [])

    parts: List[str] = []
    parts.append("【项目上下文】以下是当前项目的完整 7 件基座 + 章节摘要，请基于这些数据工作。")
    parts.append("")

    # 1. world_tree
    wt = project_data.get("world_tree", {})
    parts.append("── 1. world_tree（世界树）──")
    parts.append(_format_world_tree_compact(wt))
    parts.append("")

    # 2. style_pack（笔风 id + 名称，完整笔风在 system_prompt 里）
    pack_id = _get_project_style_pack_id(project_id)
    pack = get_style_pack_or_default(pack_id)
    parts.append("── 2. style_pack（写作笔风）──")
    parts.append(f"  id: {pack['id']}")
    parts.append(f"  名称: {pack['name']}")
    parts.append(f"  标语: {pack['tagline']}")
    parts.append("")

    # 3. genre_resonance
    gr = project_data.get("genre_resonance", {})
    parts.append("── 3. genre_resonance（题材共振）──")
    if gr:
        accept = gr.get("accept", [])
        reject = gr.get("reject", [])
        anchors = gr.get("anchors", [])
        if accept:
            parts.append(f"  接纳: {', '.join(str(a) for a in accept)}")
        if reject:
            parts.append(f"  拒绝: {', '.join(str(r) for r in reject)}")
        if anchors:
            parts.append(f"  锚点: {', '.join(str(a) for a in anchors)}")
    else:
        parts.append("  （空）")
    parts.append("")

    # 4. main_plot
    mp = project_data.get("main_plot", {})
    parts.append("── 4. main_plot（主线）──")
    parts.append(_format_main_plot(mp))
    parts.append("")

    # 5. sub_plot
    sp = project_data.get("sub_plot", {})
    sp_threads = sp.get("threads", []) if isinstance(sp, dict) else []
    parts.append("── 5. sub_plot（支线）──")
    parts.append(_format_sub_plot(sp_threads))
    parts.append("")

    # 6. character_card
    cc = project_data.get("character_card", {})
    cc_chars = cc.get("characters", []) if isinstance(cc, dict) else []
    parts.append("── 6. character_card（角色卡）──")
    parts.append(_format_characters(cc_chars))
    parts.append("")

    # 7. seed_table
    st = project_data.get("seed_table", {})
    st_seeds = st.get("seeds", []) if isinstance(st, dict) else []
    parts.append("── 7. seed_table（伏笔种子）──")
    parts.append(_format_seeds(st_seeds))
    parts.append("")

    # 章节摘要
    parts.append("── 章节摘要 ──")
    if agent_name == "novel_writer":
        parts.append(_format_chapter_summaries_graded(chapters))
    else:
        parts.append(_format_chapter_summaries_short(chapters))

    return "\n".join(parts)

