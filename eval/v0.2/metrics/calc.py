"""
calc.py - 5 个核心指标计算器

按 04 §6.2 蕾姆自定：
1. 种子回收率（一致性）—— 埋下的种子在 N 章内被再次提及的比例
2. 基座约束遵守率（一致性）—— 违反 hard 规则的比例
3. 具体性颗粒密度（沉浸感）—— 每千字的具体性颗粒数
4. overdue 触发命中率（种子加权）—— overdue_score >= 0.7 的种子在下一章 prompt 中出现的比例
5. importance 优先采纳率（种子加权）—— importance=主线推进 的种子被 LLM 选用的比例
"""
import json
import re
from typing import Dict, List


# === 指标 1: 种子回收率 ===
def metric_seed_recovery(seed_table: Dict, chapter_summaries: List[Dict]) -> Dict:
    """
    04 §2.1 种子回收率 = 回收数 / 埋下数
    简化定义：种子的 status 变为 resonating（强化 1+ 次）或 harvested 算"被回收"
    """
    seeds = seed_table.get("seeds", [])
    if not seeds:
        return {"value": 0.0, "recovered": 0, "total": 0, "detail": "无种子"}

    recovered = sum(1 for s in seeds if s["status"] in ("resonating", "harvested"))
    total = len(seeds)
    rate = recovered / total if total > 0 else 0.0

    return {
        "value": round(rate, 3),
        "recovered": recovered,
        "total": total,
        "target": 0.70,
        "passed": rate >= 0.70,
        "detail": f"{recovered}/{total} 个种子被强化或回收",
    }


# === 指标 2: 基座约束遵守率 ===
def metric_base_rule_compliance(
    world_tree: Dict, chapter_texts: List[str]
) -> Dict:
    """
    04 §2.1 基座约束遵守率 = 1 - 违反次数 / 总章数
    简化检测：枚举 hard 规则的"违反关键词"
    """
    rules = world_tree.get("base", {}).get("core_rules", [])
    hard_rules = [r for r in rules if r["enforcement"] == "hard"]

    if not hard_rules:
        return {"value": 1.0, "violations": 0, "total_chapters": len(chapter_texts), "detail": "无 hard 规则"}

    # 关键词字典（hard 规则对应可能违反的关键词）
    violation_keywords = {
        "无超自然": ["魔法", "仙术", "法术", "神力", "妖", "灵异", "穿越者", "重生者"],
        "现代都市": ["皇宫", "门派", "修炼", "灵气", "飞剑", "魂穿"],
        "现实主义": ["系统", "金手指", "签到", "开局获得"],
    }

    violations = 0
    violation_details = []
    for i, text in enumerate(chapter_texts, 1):
        for rule in hard_rules:
            kw_list = violation_keywords.get(rule["statement"], [])
            found = [kw for kw in kw_list if kw in text]
            if found:
                violations += 1
                violation_details.append(f"第 {i} 章违反「{rule['statement']}」: {found}")
                break  # 一章算一次违反

    total = len(chapter_texts)
    rate = 1 - (violations / total) if total > 0 else 1.0

    return {
        "value": round(rate, 3),
        "violations": violations,
        "total_chapters": total,
        "target": 1.0,
        "passed": violations == 0,
        "detail": "; ".join(violation_details) if violation_details else "无违反",
    }


# === 指标 3: 具体性颗粒密度 ===
def metric_specificity_density(chapter_texts: List[str]) -> Dict:
    """
    04 §2.2 具体性颗粒密度 = 具体词/数字/专有名词总数 / 字数 × 1000
    目标: ≤ 3 / 千字
    简化：检测数字 + 引号内的具体名词
    """
    # 数字模式
    num_pattern = re.compile(r"\d+(\.\d+)?")
    # 引号内具体名词
    quote_pattern = re.compile(r'["""]([^"""]+)["""]')

    total_chars = 0
    total_granules = 0
    chapter_details = []

    for i, text in enumerate(chapter_texts, 1):
        nums = num_pattern.findall(text)
        quotes = quote_pattern.findall(text)
        granules = len(nums) + len(quotes)
        chars = len(text)
        density = (granules / chars * 1000) if chars > 0 else 0.0

        total_chars += chars
        total_granules += granules
        chapter_details.append({
            "chapter": i,
            "granules": granules,
            "chars": chars,
            "density": round(density, 2),
        })

    overall_density = (total_granules / total_chars * 1000) if total_chars > 0 else 0.0

    return {
        "value": round(overall_density, 2),
        "total_granules": total_granules,
        "total_chars": total_chars,
        "target": 3.0,
        "target_comparison": "<=",
        "passed": overall_density <= 3.0,
        "chapter_details": chapter_details,
        "detail": f"{total_granules} 颗粒 / {total_chars} 字 = {overall_density:.2f} / 千字",
    }


# === 指标 4: overdue 触发命中率 ===
def metric_overdue_hit_rate(
    seed_table: Dict, chapter_summaries: List[Dict]
) -> Dict:
    """
    04 §2.3 overdue 触发命中率 = 命中数 / overdue 数
    简化：overdue_score >= 0.7 的种子在下一章的 key_events 里被提到 = 命中
    """
    # 由于我们没有真实的 prompt log，用 seed.status 变化近似
    seeds = seed_table.get("seeds", [])
    if not seeds:
        return {"value": 0.0, "hit": 0, "overdue": 0, "detail": "无种子"}

    # 模拟 overdue 状态：当前 segment > planted + planned_interval
    overdue_seeds = []
    for s in seeds:
        overdue = max(0, s["last_seen_segment"] - s["planted_at_segment"] - s["planned_interval"])
        if overdue > 0:
            overdue_seeds.append(s)

    # 命中：状态变为 resonating 或 harvested
    hit = sum(1 for s in overdue_seeds if s["status"] in ("resonating", "harvested"))
    total = len(overdue_seeds)

    rate = hit / total if total > 0 else 0.0

    return {
        "value": round(rate, 3),
        "hit": hit,
        "overdue": total,
        "target": 0.90,
        "passed": rate >= 0.90,
        "detail": f"{hit}/{total} 个 overdue 种子被回收",
    }


# === 指标 5: importance 优先采纳率 ===
def metric_importance_priority(
    seed_table: Dict, chapter_summaries: List[Dict]
) -> Dict:
    """
    04 §2.3 importance 优先采纳率 = 选用数 / 主线推进种子数
    简化：主线推进种子的 status 是否 >= resonating
    """
    seeds = seed_table.get("seeds", [])
    if not seeds:
        return {"value": 0.0, "adopted": 0, "main_count": 0, "detail": "无种子"}

    main_seeds = [s for s in seeds if s["importance"]["primary"] == "主线推进"]
    adopted = sum(1 for s in main_seeds if s["status"] in ("resonating", "harvested"))
    total = len(main_seeds)

    rate = adopted / total if total > 0 else 0.0

    return {
        "value": round(rate, 3),
        "adopted": adopted,
        "main_count": total,
        "target": 0.80,
        "passed": rate >= 0.80,
        "detail": f"{adopted}/{total} 个主线种子被强化或回收",
    }


def update_seed_table(
    seed_table: Dict,
    chapter_summaries: List[Dict],
    current_segment: int,
) -> Dict:
    """
    02 §4.4 种子状态自动更新
    根据 chapter_summaries 更新 seed 状态
    """
    updated = dict(seed_table)
    updated["seeds"] = [dict(s) for s in seed_table["seeds"]]

    for s in updated["seeds"]:
        for summary in chapter_summaries:
            planted_ids = summary.get("seed_changes", {}).get("planted", [])
            resonating_ids = summary.get("seed_changes", {}).get("resonating", [])
            harvested_ids = summary.get("seed_changes", {}).get("harvested", [])

            if s["id"] in resonating_ids:
                s["status"] = "resonating"
                s["last_seen_segment"] = current_segment
                s["last_seen_chapter"] = summary["chapter_id"]
            elif s["id"] in planted_ids:
                s["planted_at_segment"] = current_segment
                s["planted_at_chapter"] = summary["chapter_id"]
            elif s["id"] in harvested_ids:
                s["status"] = "harvested"
                s["last_seen_segment"] = current_segment
                s["last_seen_chapter"] = summary["chapter_id"]

    return updated


def calc_all_metrics(
    world_tree: Dict,
    style_charter: Dict,
    genre_resonance: Dict,
    seed_table: Dict,
    chapter_texts: List[str],
    chapter_summaries: List[Dict],
) -> Dict:
    """计算 5 个核心指标"""
    return {
        "1_种子回收率": metric_seed_recovery(seed_table, chapter_summaries),
        "2_基座约束遵守率": metric_base_rule_compliance(world_tree, chapter_texts),
        "3_具体性颗粒密度": metric_specificity_density(chapter_texts),
        "4_overdue_触发命中率": metric_overdue_hit_rate(seed_table, chapter_summaries),
        "5_importance_优先采纳率": metric_importance_priority(seed_table, chapter_summaries),
    }


if __name__ == "__main__":
    import os

    # 用模拟数据测试
    case_dir = "../cases/case-1-urban-romance"
    world_tree = json.load(open(os.path.join(case_dir, "01-world-tree.json")))
    style_charter = json.load(open(os.path.join(case_dir, "02-style-charter.json")))
    genre_resonance = json.load(open(os.path.join(case_dir, "03-genre-resonance.json")))
    seed_table = json.load(open(os.path.join(case_dir, "07-seed-table.json")))

    # 模拟 5 章
    chapter_texts = [
        "1987 年的那台收音机还在纸箱里。",
        '母亲说："这东西你爸从来不让扔。"',
        "主角和老周在街角早餐店吃了碗面。",
        "公司里开始有人讨论跳槽。",
        "主角回家后独自听那台老收音机。",
    ]

    # 模拟种子状态更新
    updated_seeds = []
    for s in seed_table["seeds"]:
        s = dict(s)
        if s["id"] == 1:  # 收音机
            s["status"] = "resonating"
            s["last_seen_segment"] = 12
        elif s["id"] == 2:  # 父亲的信
            s["status"] = "planted"
            s["last_seen_segment"] = 0
        elif s["id"] == 3:  # 早餐店
            s["status"] = "harvested"
            s["last_seen_segment"] = 3
        updated_seeds.append(s)

    seed_table_updated = dict(seed_table)
    seed_table_updated["seeds"] = updated_seeds

    chapter_summaries = [{"chapter_id": i + 1, "key_events": ["事件"]} for i in range(5)]

    metrics = calc_all_metrics(
        world_tree, style_charter, genre_resonance,
        seed_table_updated, chapter_texts, chapter_summaries,
    )

    print("=== 5 个核心指标（模拟数据）===")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
