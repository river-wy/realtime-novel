"""seed_weight.py — 种子权重计算器（从 eval/v0.2/pipeline/seed_weight.py 抽出）

按 docs/design/02-consistency.md §2.2 4 维加权求和
+ §2.3 双重缩放 + sigmoid
按当前 segment/章节数重算每个种子的 weight
"""
from __future__ import annotations

import math
from typing import Dict, List


# 02 §2.4 重要性预设数值表
IMPORTANCE_SCORES = {
    "主线推进": 1.0,
    "支线故事": 0.6,
    "小巧思": 0.2,
}

# 02 §2.5 种子大小预设数值表
SIZE_SCORES = {
    "长线": 1.0,
    "中线": 0.6,
    "点状": 0.2,
}

# 02 §2.6 种子导向预设数值表
ORIENTATION_SCORES = {
    "剧情翻转": 1.0,
    "关键成员关系": 0.8,
    "主角成长": 0.6,
    "支线揭示": 0.4,
    "小巧思": 0.2,
    "氛围营造": 0.1,
}


def sigmoid(x: float, k: float = 2.0) -> float:
    """sigmoid 函数，k=2 是 v0.1 斜率参数"""
    return 1.0 / (1.0 + math.exp(-k * x))


def calc_overdue_score(seed: Dict, current_segment: int) -> float:
    """
    02 §2.3 双重缩放 + sigmoid
    overdue = max(0, current - planted - planned)
    normalized = overdue / sqrt(planned)
    overdue_score = sigmoid(normalized × k)
    """
    overdue = max(0, current_segment - seed["planted_at_segment"] - seed["planned_interval"])
    if seed["planned_interval"] == 0:
        return 0.5
    normalized = overdue / math.sqrt(seed["planned_interval"])
    return sigmoid(normalized)


def calc_weight(seed: Dict, current_segment: int) -> float:
    """
    02 §2.2 4 维加权求和
    weight = overdue_score × 0.4 + importance × 0.25 + size × 0.2 + orientation × 0.15
    """
    overdue_score = calc_overdue_score(seed, current_segment)

    # importance 是双层 enum：取 primary
    importance_primary = seed["importance"]["primary"]
    importance_score = IMPORTANCE_SCORES.get(importance_primary, 0.5)

    size_score = SIZE_SCORES.get(seed["size"], 0.5)
    orientation_score = ORIENTATION_SCORES.get(seed["orientation"], 0.5)

    weight = (
        overdue_score * 0.4
        + importance_score * 0.25
        + size_score * 0.20
        + orientation_score * 0.15
    )
    return round(weight, 3)


def rank_seeds(seeds: List[Dict], current_segment: int) -> List[Dict]:
    """
    按 weight 降序排，附加 02 §2.8 阈值行为
    - weight >= 0.7: "强制"（must）
    - 0.3 <= weight < 0.7: "可选"（optional）
    - weight < 0.3: "不进 prompt"（drop）
    """
    for seed in seeds:
        seed["weight"] = calc_weight(seed, current_segment)
        if seed["weight"] >= 0.7:
            seed["priority"] = "must"
        elif seed["weight"] >= 0.3:
            seed["priority"] = "optional"
        else:
            seed["priority"] = "drop"

    return sorted(seeds, key=lambda s: s["weight"], reverse=True)
