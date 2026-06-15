"""three_layer_prompt.py — 三层 prompt 组装器（从 eval/v0.2/pipeline 抽出）

按 docs/design/02-consistency.md §1：
- 基座层（800t）：世界树 + 风格宪法 + 题材共鸣
- 动态调参层（1200t）：当前种子权重清单 + 阶段摘要 + 密度配比
- 最近轮次层（2000t）：最近 N 章极简摘要 + 最近 1 章全文

输入统一接受 Pydantic 模型（产品侧），内部统一转为 dict 复用 v0.2 逻辑
"""
from __future__ import annotations

from typing import Dict, List, Optional, Union

from ..core.schemas import (
    WorldTreeSchema,
    StyleCharterSchema,
    GenreResonanceSchema,
    MainPlotSchema,
    CharacterCardSchema,
    SeedTableSchema,
)
from .seed_weight import rank_seeds


# === 三个单层 ===

def build_base_layer(
    world_tree: Union[WorldTreeSchema, dict],
    style_charter: Union[StyleCharterSchema, dict],
    genre_resonance: Union[GenreResonanceSchema, dict],
) -> str:
    """02 §1.2.1 基座层（永远在 prompt 头部）"""
    wt = _to_dict(world_tree)
    sc = _to_dict(style_charter)
    gr = _to_dict(genre_resonance)

    # 核心规则
    rules = []
    for r in wt.get("base", {}).get("core_rules", []):
        rules.append(f"- [{r['enforcement']}] {r['statement']}")
    rules_text = "\n".join(rules) if rules else "（无显式规则）"

    # 风格宪法
    prose = sc.get("prose_style", {})
    tone = sc.get("tone", {})
    density = sc.get("density", {})
    limits = sc.get("limits", {})

    style_text = f"""散文风格：{prose.get('primary', '散文式')}
句式：{prose.get('sentence_length', '长短交错')}
段落：{prose.get('paragraph_style', '每段聚焦一个画面')}

语气：{tone.get('primary', '冷叙述')}（{tone.get('secondary', '')}）
心理活动 ≤ {tone.get('psychological_per_paragraph', 3)} 句/段

密度配比：
- 具体性 {density.get('specificity', 0.7)}
- 主观性 {density.get('subjectivity', 0.6)}
- 密度 {density.get('density', 0.5)}
- 题材共鸣 {density.get('genre_resonance', 0.8)}
- 具体性颗粒硬上限 ≤ {density.get('max_specific_granules_per_kchars', 3)} / 千字

硬约束：
- 心理活动 ≤ {limits.get('psychological_per_paragraph', 3)} 句/段
- 具体性颗粒 ≤ {limits.get('specific_granules_per_kchars', 3)} / 千字
- 章节字数 {limits.get('min_chapter_words', 2500)} - {limits.get('max_chapter_words', 3000)}"""

    # 题材共鸣
    accept_items = [f"+ {a['text']}" for a in gr.get("accept", [])]
    reject_items = [f"- {r['text']}" for r in gr.get("reject", [])]
    anchors = [a["phrase"] for a in gr.get("anchors", [])]

    resonance_text = f"""接受：
{chr(10).join(accept_items) if accept_items else '（无）'}

拒绝：
{chr(10).join(reject_items) if reject_items else '（无）'}

用户原文锚定：
{chr(10).join('- ' + a for a in anchors) if anchors else '（无）'}"""

    # 世界树
    timeline = wt.get("base", {}).get("timeline", {})
    geography = wt.get("base", {}).get("geography", {})

    world_text = f"""时间：{timeline.get('era', '现代')} {timeline.get('anchor_event', '')}
地理：{geography.get('primary', '杭州')}（{', '.join(geography.get('secondary', []))}）
空间约束：{', '.join(geography.get('spatial_rules', [])) or '（无）'}"""

    base_layer = f"""=== 基座层（永远在）===

## 世界树基座
{world_text}

## 核心规则
{rules_text}

## 风格宪法
{style_text}

## 题材共鸣
{resonance_text}
"""
    return base_layer


def build_dynamic_layer(
    seeds: List[Dict],
    current_segment: int,
    style_charter: Union[StyleCharterSchema, dict],
) -> str:
    """02 §1.2.2 动态调参层（每章重算）"""
    sc = _to_dict(style_charter)
    ranked = rank_seeds(seeds, current_segment)

    must_seeds = [s for s in ranked if s["priority"] == "must"]
    optional_seeds = [s for s in ranked if s["priority"] == "optional"]

    seed_lines = []
    for i, s in enumerate(must_seeds + optional_seeds, 1):
        marker = "【必须】" if s["priority"] == "must" else "【可选】"
        seed_lines.append(
            f"{i}. {marker} 种子 #{s['id']}「{s['content']}」 "
            f"[权重 {s['weight']}] "
            f"importance={s['importance']['primary']} "
            f"size={s['size']} orientation={s['orientation']}"
        )
    seed_text = "\n".join(seed_lines) if seed_lines else "（无活跃种子）"

    density = sc.get("density", {})

    dynamic_layer = f"""=== 动态调参层（每章重算）===

## 当前活跃种子（按权重降序）
{seed_text}

## 当前密度配比
- 具体性 {density.get('specificity', 0.7)}
- 主观性 {density.get('subjectivity', 0.6)}
- 密度 {density.get('density', 0.5)}
- 题材共鸣 {density.get('genre_resonance', 0.8)}
- 具体性颗粒硬上限 ≤ {density.get('max_specific_granules_per_kchars', 3)} / 千字
"""
    return dynamic_layer


def build_recent_layer(
    chapter_summaries: List[Dict],
    last_chapter_full: Optional[str],
) -> str:
    """02 §1.2.3 最近轮次层（滚动窗口）"""
    summary_lines = []
    for s in chapter_summaries:
        summary_lines.append(f"- 第 {s['chapter_id']} 章: {' / '.join(s.get('key_events', []))}")

    summary_text = "\n".join(summary_lines) if summary_lines else "（无历史章节）"

    last_text = last_chapter_full if last_chapter_full else "（无上一章）"

    recent_layer = f"""=== 最近轮次层（滚动）===

## 最近章节摘要
{summary_text}

## 最近 1 章全文
{last_text[:2000] if len(last_text) > 2000 else last_text}
"""
    return recent_layer


def build_full_prompt(
    world_tree: Union[WorldTreeSchema, dict],
    style_charter: Union[StyleCharterSchema, dict],
    genre_resonance: Union[GenreResonanceSchema, dict],
    seeds: List[Dict],
    character_card: Union[CharacterCardSchema, dict],
    main_plot: Union[MainPlotSchema, dict],
    current_segment: int,
    chapter_summaries: List[Dict],
    last_chapter_full: Optional[str],
    user_input: str,
) -> str:
    """
    组装完整的三层 prompt + 用户输入
    02 §1.3 拼接顺序：人物 + 基座 → 动态 → 最近 → 用户输入
    v0.2 修复: 人物设定放进 prompt 头部，防止 LLM 改名字
    """
    base = build_base_layer(world_tree, style_charter, genre_resonance)
    dynamic = build_dynamic_layer(seeds, current_segment, style_charter)
    recent = build_recent_layer(chapter_summaries, last_chapter_full)

    # === 人物设定（v0.2 新增，放最前面防止 LLM 自由发挥）===
    cc = _to_dict(character_card)
    char_lines = []
    for c in cc.get("characters", []):
        char_lines.append(
            f"- 【重要】主角/重要人物名字必须是「{c['name']}」 (id={c['id']}, role={c['role']}): {c['background'][:100]}"
        )
    chars_text = "\n".join(char_lines)

    # === 当前 beat（防止 LLM 跑偏主线）===
    mp = _to_dict(main_plot)
    current_beat = None
    for b in mp.get("beats", []):
        if b.get("status") == "active":
            current_beat = b
            break
    if not current_beat and mp.get("beats"):
        current_beat = mp["beats"][0]
    beat_text = ""
    if current_beat:
        beat_text = f"""## 当前主线节拍
- ID: {current_beat['id']}
- 标题: {current_beat['title']}
- 描述: {current_beat['description']}
- 期望人物变化: {current_beat['expected_arc']}"""

    # === 种子 ID 清单（让 LLM 在 key_events 里能引用）===
    seed_id_list = ", ".join([f"#{s['id']}「{s['content']}」" for s in seeds])

    full = f"""=== 人物设定（最高优先级 · 不要改名字）===
{chars_text}

{base}

{dynamic}

{recent}

{beat_text}

=== 种子 ID 清单 ===
本章如果遇到下列种子，请在 key_events 中以「种子 #N」形式提及，便于程序跟踪：
{seed_id_list}

=== 用户输入 ===
{user_input}

=== 输出要求 ===
请生成下一章正文，~3000 字散文式。
"""
    return full


# === 工具函数 ===

def _to_dict(obj):
    """Pydantic 模型 → dict；dict 本身 → 原样返回"""
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    return obj
