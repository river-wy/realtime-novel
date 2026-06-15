"""
seed_weight.py - 种子权重计算器（02 §2.2 4 维加权求和 + §2.3 双重缩放 + sigmoid）

按当前 segment/章节数重算每个种子的 weight
"""
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


if __name__ == "__main__":
    # 02 §2.7 示例验证
    seeds = [
        {
            "id": 1, "content": "收音机",
            "importance": {"primary": "主线推进"},
            "size": "中线", "planned_interval": 10, "orientation": "主角成长",
            "planted_at_segment": 0,
        },
        {
            "id": 2, "content": "父亲的信",
            "importance": {"primary": "主线推进"},
            "size": "长线", "planned_interval": 5, "orientation": "关键成员关系",
            "planted_at_segment": 0,
        },
        {
            "id": 3, "content": "街角早餐店",
            "importance": {"primary": "支线故事"},
            "size": "点状", "planned_interval": 3, "orientation": "氛围营造",
            "planted_at_segment": 0,
        },
    ]
    ranked = rank_seeds(seeds, current_segment=0)
    print("=== 02 §2.7 示例验证（current_segment=0）===")
    for s in ranked:
        print(f"种子 #{s['id']} {s['content']}: weight={s['weight']}, priority={s['priority']}")
