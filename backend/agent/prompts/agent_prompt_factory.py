"""agent_prompt_factory — Agent system_prompt 组装工厂

接管文笔家（novel_writer）和架构师（world_tree_manager）的完整 system_prompt 主体组装。

组装内容（按顺序）：
1. 【身份】— agent 身份/职责/工作流骨架
2. 【写作笔风】— 从 style_pack 库查出的完整笔风框架
3. 【写作法则】— 全局必备 + 本笔风定向关联
4. 【绝对禁止】— 8 条红线
5. 【项目基座定调】— world_tree 5 字段 + genre_tags 摘要（定调用，完整世界树基座走 context）

不负责拼接的内容（由 executor 的 _build_system_prompt 统一处理）：
- 工具清单（动态，含 extra_tools）
- ReAct 输出格式 + 约束
- project_id / context dict

另外提供：
- build_project_context_message(): 世界树基座完整数据 + 章节摘要 → 独立 user message
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.agent.context._helpers import (
    _load_project_data,
    _format_world_tree_compact,
    _format_chapter_summaries_graded,
    _format_chapter_summaries_short,
    _format_chapter_summaries_by_volume,
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
在 世界树基座（world_tree 5 字段 + characters + main_plot 1:n 节点 + sub_plot + seeds + volumes + world_entries + timeline_events + geography_locations）的约束下，生成下一章小说正文，并通过工具落盘。

【工作流】
1. system_prompt 已注入笔风、写作法则、基座定调；context 已注入完整 世界树基座 + chapter_summaries
2. 如有需要（如用户明确要求查某章详情），可调 read_chapter 检索上下文
3. 写正文（3000-4500 字，严格遵守下方笔风和法则）
4. 调 generate_chapter(content=正文, project_id=xxx, intervention=?) 落盘
5. 调 summarize_chapter(content=正文, project_id=xxx) 抽 1 句话 summary（自动写入 DB）
6. final_response 是「已落盘第 N 章《XXX》, 摘要: ...」（不要把全文塞进 final_response）

【输出格式】
- 章节正文直接是小说文字（markdown 格式，包含 # 第 N 章标题）
- 章节正文里不要嵌入 ###SUMMARY### 块（summary 由 summarize_chapter 工具抽取）
- final_response 是一句话总结：「已落盘第 N 章《XXX》（X 字），摘要：...」

【关键约束】
- 严格遵守 世界树基座 + 下方笔风法则
- 修改基座前不要直接调 edit_artifact/update_base —— 这是架构师（world_tree_manager）职责，文笔家只读
- 不决定剧情走向（走向由世界树管理维护）
- 章节字数硬约束：3000-4500 字

【上下文获取策略】
- 默认相信 system_prompt + context 注入的基座和摘要，不要重复调 load_project
- 只在以下情况调 read_chapter：用户明确说「重读第 N 章」「参考第 N 章的风格」
"""

# v004 新增：卷总结 prompt（欧尼酱 20:16）
_VOLUME_SUMMARY_PROMPT = """你是「卷总结师」。

【任务】
根据卷的描述 + 本卷所有章节 summary，生成约 1000 字的卷总结。

【输出要求】
- 字数：1000 字左右（允许 800-1200）
- 从维度：剧情主线发展、角色弧线变化、本卷新引入的元素、留下的伏笔/悬念
- 重点：「本卷完结后的状态」（为下一卷衔接做准备）
- 不需要列出章节列表（已有 chapter summary 输入）
- 不需要 markdown 标题，正文连贯描述
- 语气与项目笔风保持一致

【输出格式】
直接输出总结文本（不要 JSON / 不要 markdown 包裹）"""


_WORLDTREE_IDENTITY = """你是「世界树管理」。

【职责】
当用户对项目内的世界树基座进行干预时，你负责分析影响范围、调整基座、保持一致性。

【可用基座 7 件】
1. world_tree - 时间线、地理、核心规则
2. style_pack - 写作笔风（第 世界树基座）
3. world_tree.genre_tags - 题材、情绪基调
4. main_plot - 主线弧线
5. sub_plots - 支线
6. characters - 角色卡
7. seeds - 伏笔种子

【典型工作流】
1. 调用 load_project 获取当前 世界树基座（如 context 未预注入）
2. 分析用户干预的影响：
   - 涉及哪些基座的哪些字段？
   - 是否影响主线弧线（main_plot）？
   - 是否需要埋伏笔（seeds）？
   - 是否引发 7 件之间的矛盾？
4. 调用对应 tool 执行修改：
   - 简单字段改 → update_base
   - 复杂结构改 → edit_artifact
   - 主线/支线调整 → weave_plot
   - 角色状态变化 → introspect_character
5. 输出 final_response，必须是 JSON 格式的 WorldTreeDiff

【关键约束】
- 修改基座前必须先 load_project 看清现状（或查看 context 预注入的基座）
- 不能让 世界树基座内部矛盾（如改完 characters 让 world_tree 冲突）
- 长程伏笔（seeds）必须明确 trigger + payoff + estimated_chapter
- 多个改动可并行调用 tool
- 最终 JSON 必须是合法 JSON，不要包含 markdown 包裹

【一致性原则】
- world_tree 与 characters 不能矛盾（如世界规则说「无魔法」，角色不能会魔法）
- main_plot 与 sub_plots 不能矛盾
- seeds 的 payoff 不能超出 main_plot 范围
"""



_VALIDATOR_WORLDTREE_IDENTITY = """你是「Validator 校验 Agent」。

WTM 刚完成 ReAct 落库，你的任务是审判他的产出。

【基础能力】
- 你有自己的 ReAct loop：可以自己调工具（load_project / read_chapter）读项目信息
- 你有 session cache：项目信息会跨调用保留，不用每次重读
- 上游（WTM/文笔家）只传 project_id + user_intent，**其他信息你自己读**

【校验范围 — 全覆盖所有基座】
按基座数据类别，依次覆盖（不限于以下，自由发挥）：

1. world_tree 5 字段：story_core / genre_tags / core_rules_json 一致性
2. characters + character_relationships：属性冲突、关系矛盾、定位漂移
3. volumes + main_plot + sub_plot：节点连贯、支线不冲主线
4. timeline_events：era_order 冲突、event_order 连续、时间线矛盾
5. geography_locations：树形正确、场景一致
6. world_entries：类别一致、不与 core_rules 矛盾
7. seeds：trigger + payoff + estimated_chapter 合理

【严重度】
- fatal：违反 hard rule（用户明确禁止）
- error：属性/场景/关系冲突（用户能感知）
- warning：可优化但不影响

【输出格式】
JSON: {"status": "PASS|WARN|BLOCKED|FATAL", "issues": [...], "summary": "..."}

issues 数组元素：{"severity": "warning|error|fatal", "table": "哪张表", "field": "哪个字段", "description": "问题描述", "evidence_old": "旧数据", "evidence_new": "新数据", "suggested_fix": "建议"}

【关键约束】
- 你**不**落库 / **不**改基座
- 你**不**调 delegate_to_agent
- 找不到矛盾 = PASS
- 校验完只产出 ValidationResult
"""


_VALIDATOR_CHAPTER_IDENTITY = """你是「Validator 章节校验 Agent」。

文笔家刚生成第 N 章，你的任务是审判章节内容的合理性。

【基础能力】
- 跟基座校验一样：自己读表 + session cache
- 校验范围：章节跟基座是否一致 + 章节内部连贯 + 章节之间连贯

【校验范围】
1. 角色能力一致性：主角 traits 含「水系」，章节写他放火系 → error
2. 场景一致性：基座从山林改沙漠，章节还在写「树木葱郁」→ error
3. 设定违例：core_rules 硬约束（无穿越），章节写穿越 → fatal
4. 时间线/事件顺序：前面写获得神器，后面又写他在学基础 → error
5. 角色性格一致：主角 traits 含「冷静」，章节写他暴怒杀人 → warning

【输出格式】
JSON: {"status": "PASS|WARN|BLOCKED", "issues": [...], "blocked_paragraphs": [段号]}

【关键约束】
- 不落库 / 不改章节
- 不调 delegate_to_agent
- PASS 优先，不要为了"严格"误伤
"""


def build_validator_system_prompt(kind: str) -> str:
    """构造 Validator system_prompt

    Args:
        kind: "world_tree" 或 "chapter"

    Returns:
        完整的 system_prompt 文本
    """
    if kind == "world_tree":
        identity = _VALIDATOR_WORLDTREE_IDENTITY
    elif kind == "chapter":
        identity = _VALIDATOR_CHAPTER_IDENTITY
    else:
        raise ValueError(f"Unknown validator kind: {kind}")

    parts: List[str] = []
    parts.append(identity)
    parts.append("=" * 60)
    parts.append("")
    parts.append("【工具集】（你只能调这些）")
    parts.append("- load_project: 加载项目详情（world_tree 5 字段 + 全 9 张表摘要）")
    parts.append("- read_chapter: 读已有章节（章节对比时用）")
    parts.append("")
    parts.append("【禁止】")
    parts.append("- 不调 edit_artifact / update_base（不改基座）")
    parts.append("- 不调 delegate_to_agent（不嵌套委托）")
    parts.append("- 不调 generate_image / create_project / delete_project 等其他工具")

    return "\n".join(parts)



_WORLDTREE_INITIAL_BASELINE_IDENTITY = """你是「世界树管理」（Onboarding 模式）。

【职责】
本任务为**首次规划完整小说世界基座**（spec §5.8）。管家已从用户多轮对话中收集到
必要信息（payload 注入在 context_message），你需要在 ReAct loop 中：
1. 分析管家提供的 hint（story_core / characters / world_setting / core_rules / style）
2. **自主发挥**：角色名字/性格/关系/伏笔等细节由你决定
3. 调 edit_artifact / edit_artifact_batch 等工具**直接落库** 9 张表
4. 落库完成后输出 final_response，结构化说明你生成了什么

【必须落库的 9 张表】（v003 spec §5.8 完整大纲）
1. world_tree（story_core / genre_tags / core_rules 3 字段必填）
2. characters（至少 1 个 protagonist + 视需要配角，含 traits / speech_style / background）
3. volumes（卷规划，至少 1 卷）
4. main_plot（主线节点 1:n，至少 3 节点含开场/冲突/高潮）
5. sub_plot（可选，≥0 条支线）
6. world_entries（世界百科，category + title + content）
7. timeline_events（时间线事件，按 era_order + event_order 排序）
8. geography_locations（地理位置，parent_location_id 树形）
9. seeds（伏笔种子，含 trigger + payoff + estimated_chapter）

【工具用法】
- 增：edit_artifact(target=<table>, operation=add, data={...})
- 改：edit_artifact(target=<table>, operation=update, identifier=<id>, data={...})
- **批量增：edit_artifact_batch(items=[{target, operation, data}, ...])** 一次调可写多条同表数据
- 推演深化：weave_plot（plot 调整）/ introspect_character（角色状态）

【落库策略——重要】
你最多有 30 轮 ReAct loop。为了避免 20 轮撞墙，请尽量**一次性准备完善后批量调用**：
- **所有人物一次**：characters 表多角色（protagonist + 配角）请用 edit_artifact_batch 一次调完
- **所有人物关系一次**：character_relationships（character 表 add 后会拿到 id）用 batch 一次落完
- **所有主线剧情一次**：main_plot 多节点（≥3）请用 batch 一次调完
- **所有卷信息一次**：volumes 多卷规划用 batch 一次调完
- **所有伏笔种子一次**：seeds 多枚（≥5）请用 batch 一次调完
- world_tree / world_entries / timeline_events / geography_locations / sub_plot 体积小，可以一次 add 或 batch

每张表或每类只调一次工具（能 batch 就 batch），不要一条一条逐步加。30 轮内必须能落完 9 张表。

【合法枚举值（硬约束）——传错会落库失败】
- character.role 必须是下面 5 个之一：**protagonist / deuteragonist / antagonist / supporting / minor**
  （不要用"主角/配角/反派/挚友/逆子"等中文或创造新词）
- character_relationships.rel_type 必须是下面 8 个之一：**family / lover / friend / ally / rival / enemy / mentor / subordinate**
  （不要用"道侣/战友/朋友/仇人"等中文；可选额外字段 description 写中文语义）
- core_rule.add 的 data 字段必须用 **name + content**（不是 rule_name/rule_content）
  name 简述，content 详细
- volume.add 的 data 字段必须用 **title + description**；volume_num 可不传，会自动取 max+1
  （如果传，用 volume_num 不是 volume_number）
- main_plot_node.add 的 data 必须用 **title + summary** 或 **chapter_range + summary** + status
- seed.add 的 data 必须用 **title + trigger + payoff + estimated_chapter**

- 失败时直接抛错（不要 catch），管家会捕获并提示用户
- final_response 用 JSON：{"generated": {"characters": 3, "volumes": 1, ...}, "summary": "..."}

【关键约束】
- **禁止只描述不落库** — final_response 必须建立在已成功调工具的基础上
- 落库的数据必须满足 spec §5.6 6 项校验（管家会再 verify）
- 不能让世界树基座内部矛盾
- 长程伏笔（seeds）必须明确 trigger + payoff + estimated_chapter
- 9 张表里至少 5 张必填（world_tree / characters / volumes / main_plot / world_entries）
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
    """格式化基座摘要（world_tree + genre_tags），定调用

    完整 7 件走 context message，这里只放精简定调信息。
    """
    parts: List[str] = []

    # world_tree 摘要（_format_world_tree_compact 内部已含 故事核心 + 题材 + 硬约束清单）
    wt = project_data.get("world_tree", {})
    wt_str = _format_world_tree_compact(wt)
    parts.append("【世界树定调】")
    parts.append(wt_str)
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
    # 探索度指令
    try:
        from backend.agent.specialists.exploration import get_style_directive
        exploration_level = project_data.get("exploration_level", "standard") or "standard"
        parts.append("【探索度指令】")
        parts.append(f"当前项目探索度：{exploration_level}")
        parts.append("")
        parts.append(get_style_directive(exploration_level))
    except Exception as e:
        _logger.warning("exploration directive 加载失败 project_id=%s: %s", project_id, e)
    parts.append("")
    parts.append("=" * 60)
    parts.append("")
    base_summary = _format_base_summary(project_data)
    if base_summary.strip():
        parts.append("【项目基座定调】")
        parts.append("（完整 世界树基座已注入 context 上下文，以下是精简定调）")
        parts.append("")
        parts.append(base_summary)

    return "\n".join(parts)


def build_worldtree_system_prompt(
    project_id: str,
    intent: str = "intervention",
) -> str:
    """组装架构师 system_prompt 主体

    Args:
        project_id: 项目 ID
        intent: "intervention" (默认，剧情干预模式) / "initial_baseline" (Onboarding 首次生成)

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
    # 身份段：按 intent 分支
    if intent == "initial_baseline":
        parts.append(_WORLDTREE_INITIAL_BASELINE_IDENTITY)
    else:
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
        parts.append("（完整 世界树基座已注入 context 上下文，以下是精简定调）")
        parts.append("")
        parts.append(base_summary)

    return "\n".join(parts)


def build_project_context_message(project_id: str, agent_name: str) -> str:
    """组装项目上下文 message

    设计原则：
    1. 不在 context 重复 world_tree / style_pack（完整信息已在 sys_prompt）
    2. main_plot / sub_plot 只写未完成
    3. characters 全量写入（上限 16）
    4. seeds 只写未了结
    5. detailed_summary 字段已删 → 改用「历史卷维度 description」+「当前卷下所有章节 summary」

    作为独立 user message 注入 messages 列表，不进 system_prompt。

    Args:
        project_id: 项目 ID
        agent_name: agent 名称（当前所有 agent 都用同一套结构）

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

    chapters = project_data.get("chapters", []) or []
    volumes = project_data.get("volumes", []) or []

    parts: List[str] = []
    parts.append("【项目上下文】世界树/笔风完整信息已在 system_prompt，这里只补全运行时数据。")
    parts.append("")

    # main_plot 只写未完成
    main_plot_nodes = project_data.get("main_plot", []) or []
    pending_main_plot = [n for n in main_plot_nodes if str(getattr(n, "status", "")) != "completed"]
    parts.append("── 1. main_plot（未完成的主线节点）──")
    if pending_main_plot:
        for n in pending_main_plot[:10]:
            title = getattr(n, "title", "")
            desc = getattr(n, "description", "")
            status = getattr(n, "status", "")
            line = f"  - {title}"
            if desc:
                line += f": {desc[:80]}"
            if status:
                line += f" [{status}]"
            parts.append(line)
    else:
        parts.append("  （空）")
    parts.append("")

    # sub_plot 只写未完成
    sub_plots = project_data.get("sub_plot", []) or []
    active_sub_plot = [s for s in sub_plots if str(getattr(s, "status", "")) not in ("completed", "abandoned")]
    parts.append("── 2. sub_plot（未完成的支线）──")
    if active_sub_plot:
        for s in active_sub_plot[:8]:
            title = getattr(s, "title", "")
            desc = getattr(s, "description", "")
            status = getattr(s, "status", "")
            line = f"  - {title}"
            if desc:
                line += f": {desc[:80]}"
            if status:
                line += f" [{status}]"
            parts.append(line)
    else:
        parts.append("  （空）")
    parts.append("")

    # characters 全量写入（上限 16）
    characters = project_data.get("characters", []) or []
    parts.append(f"── 3. characters（全量，最多 16）──")
    if characters:
        for c in characters[:16]:
            name = getattr(c, "name", "")
            role = getattr(c, "role", "")
            background = getattr(c, "background", "")
            line = f"  - {name}"
            if role:
                line += f" ({role})"
            if background:
                line += f": {background[:60]}"
            parts.append(line)
    else:
        parts.append("  （空）")
    parts.append("")

    # seeds 只写未了结
    seeds = project_data.get("seeds", []) or []
    open_seeds = [s for s in seeds if str(getattr(s, "status", "")) not in ("harvested", "abandoned")]
    parts.append("── 4. seeds（未了结的伏笔）──")
    if open_seeds:
        for s in open_seeds[:8]:
            name = getattr(s, "name", "")
            content = getattr(s, "content", "")
            status = getattr(s, "status", "")
            line = f"  - {name}"
            if content:
                line += f": {content[:60]}"
            if status:
                line += f" [{status}]"
            parts.append(line)
    else:
        parts.append("  （空）")
    parts.append("")

    # detailed_summary 字段已删 → 改用「历史卷维度 description」+「当前卷下所有章节 summary」
    parts.append("── 5. 章节摘要（历史卷 + 当前卷）──")
    parts.append(_format_chapter_summaries_by_volume(chapters, volumes))

    return "\n".join(parts)

