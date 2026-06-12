"""
three_layer_prompt.py - 三层 prompt 组装器（02 §1）

- 基座层（800t）：世界树 + 风格宪法 + 题材共鸣
- 动态调参层（1200t）：当前种子权重清单 + 阶段摘要 + 密度配比
- 最近轮次层（2000t）：最近 N 章极简摘要 + 最近 1 章全文
"""
import json
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))
from seed_weight import rank_seeds


def build_base_layer(world_tree: Dict, style_charter: Dict, genre_resonance: Dict) -> str:
    """
    02 §1.2.1 基座层（永远在 prompt 头部）
    """
    # 核心规则
    rules = []
    for r in world_tree.get("base", {}).get("core_rules", []):
        rules.append(f"- [{r['enforcement']}] {r['statement']}")
    rules_text = "\n".join(rules) if rules else "（无显式规则）"

    # 风格宪法
    prose = style_charter.get("prose_style", {})
    tone = style_charter.get("tone", {})
    density = style_charter.get("density", {})
    taboos = style_charter.get("taboos", [])
    limits = style_charter.get("limits", {})

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
    accept_items = [f"+ {a['text']}" for a in genre_resonance.get("accept", [])]
    reject_items = [f"- {r['text']}" for r in genre_resonance.get("reject", [])]
    anchors = [a["phrase"] for a in genre_resonance.get("anchors", [])]

    resonance_text = f"""接受：
{chr(10).join(accept_items) if accept_items else '（无）'}

拒绝：
{chr(10).join(reject_items) if reject_items else '（无）'}

用户原文锚定：
{chr(10).join('- ' + a for a in anchors) if anchors else '（无）'}"""

    # 世界树
    timeline = world_tree.get("base", {}).get("timeline", {})
    geography = world_tree.get("base", {}).get("geography", {})

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
    style_charter: Dict,
) -> str:
    """
    02 §1.2.2 动态调参层（每章重算）
    包含：当前活跃种子（按权重排序）+ 当前密度配比
    """
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

    density = style_charter.get("density", {})

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
    """
    02 §1.2.3 最近轮次层（滚动窗口）
    """
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
    world_tree: Dict,
    style_charter: Dict,
    genre_resonance: Dict,
    seeds: List[Dict],
    current_segment: int,
    chapter_summaries: List[Dict],
    last_chapter_full: Optional[str],
    user_input: str,
) -> str:
    """
    组装完整的三层 prompt + 用户输入
    02 §1.3 拼接顺序：基座 → 动态 → 最近 → 用户输入
    """
    base = build_base_layer(world_tree, style_charter, genre_resonance)
    dynamic = build_dynamic_layer(seeds, current_segment, style_charter)
    recent = build_recent_layer(chapter_summaries, last_chapter_full)

    full = f"""{base}

{dynamic}

{recent}

=== 用户输入 ===
{user_input}

=== 输出要求 ===
请生成下一章正文，~3000 字散文式，遵守上述所有约束。
"""
    return full


if __name__ == "__main__":
    # 简单验证
    import os
    case_dir = "../cases/case-1-urban-romance"
    world_tree = json.load(open(os.path.join(case_dir, "01-world-tree.json")))
    style_charter = json.load(open(os.path.join(case_dir, "02-style-charter.json")))
    genre_resonance = json.load(open(os.path.join(case_dir, "03-genre-resonance.json")))
    seed_table = json.load(open(os.path.join(case_dir, "07-seed-table.json")))

    full = build_full_prompt(
        world_tree, style_charter, genre_resonance,
        seed_table["seeds"], current_segment=0,
        chapter_summaries=[], last_chapter_full=None,
        user_input="第 1 章：父亲遗物从老家寄到，主角在城西老小区拆箱。",
    )
    print("=== 三层 prompt 长度 ===")
    print(f"基座层: {len(build_base_layer(world_tree, style_charter, genre_resonance))} 字符")
    print(f"动态层: {len(build_dynamic_layer(seed_table['seeds'], 0, style_charter))} 字符")
    print(f"最近层: {len(build_recent_layer([], None))} 字符")
    print(f"总长: {len(full)} 字符")
    print()
    print("=== 前 1500 字预览 ===")
    print(full[:1500])
