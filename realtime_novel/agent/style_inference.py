"""v0.8.2: 风格推断 — 把用户填的 genres/styles/tone 翻译成完整 style_charter

欧尼酱拍板 (15:25): 不暴露笔法设置给用户, 由 Agent 自主推断:
- 用户填: genres (题材数组) + styles (风格数组) + tone (基调数组)
- Agent 推断: 完整 style_charter (prose_style / sentence_length / paragraph_style /
                  psychological_per_paragraph / density / limits)

推断规则:
1. 每个 style tag 有一组「笔法参数」(STYLE_PARAM_MAP)
2. 多个 style → 取交集/最大值叠加
3. tone 调整心理活动密度和主观性
4. genre 影响 limits (字数范围)

设计原则:
- 推断结果可被用户在 Reader 顶栏的「风格重生成」按钮覆盖 (v0.8.2 不做, 先 v0.9)
- 推断是 deterministic 的 (相同输入 → 相同输出)
- 推断结果会存入 style_charter 表, 后续 _format_style_charter 直接读
"""
from __future__ import annotations

from typing import Dict, List, Any


# ============ 推断规则 (v0.8.2 拍板, 可后续 LLM 化扩展) ============

# style tag → 笔法参数 (基础)
STYLE_PARAM_MAP: Dict[str, Dict[str, Any]] = {
    # 散文系 (心理活动多, 长句, 主观性强)
    "治愈":   {"prose_style": "散文式", "sentence_length": "长句为主", "paragraph_style": "每段聚焦一个画面", "psychological": 5, "subjectivity": 0.8, "specificity": 0.7},
    "唯美":   {"prose_style": "散文式", "sentence_length": "长句为主", "paragraph_style": "意象密集", "psychological": 4, "subjectivity": 0.7, "specificity": 0.8},
    "甜文":   {"prose_style": "散文式", "sentence_length": "中等", "paragraph_style": "对话+心理", "psychological": 5, "subjectivity": 0.8, "specificity": 0.6},
    "诗意":   {"prose_style": "散文式", "sentence_length": "长句为主", "paragraph_style": "意象密集", "psychological": 3, "subjectivity": 0.9, "specificity": 0.6},

    # 紧凑系 (心理活动少, 短句, 客观性强)
    "硬汉":   {"prose_style": "紧凑", "sentence_length": "短句为主", "paragraph_style": "动作驱动", "psychological": 1, "subjectivity": 0.2, "specificity": 0.8},
    "冷峻":   {"prose_style": "紧凑", "sentence_length": "短句", "paragraph_style": "白描", "psychological": 1, "subjectivity": 0.2, "specificity": 0.7},
    "悬疑":   {"prose_style": "紧凑", "sentence_length": "短句", "paragraph_style": "悬念驱动", "psychological": 3, "subjectivity": 0.5, "specificity": 0.9},
    "快节奏": {"prose_style": "紧凑", "sentence_length": "短句为主", "paragraph_style": "场景切换", "psychological": 1, "subjectivity": 0.3, "specificity": 0.7},

    # 平衡系
    "史诗":   {"prose_style": "宏大叙事", "sentence_length": "长短交错", "paragraph_style": "多场景切换", "psychological": 2, "subjectivity": 0.4, "specificity": 0.6},
    "现实":   {"prose_style": "紧凑", "sentence_length": "中等", "paragraph_style": "白描", "psychological": 3, "subjectivity": 0.5, "specificity": 0.8},
    "群像":   {"prose_style": "紧凑", "sentence_length": "长短交错", "paragraph_style": "多视角", "psychological": 3, "subjectivity": 0.5, "specificity": 0.7},
}

# tone tag → 调整项 (在 style 基础上微调)
TONE_ADJUST_MAP: Dict[str, Dict[str, Any]] = {
    "乐观":   {"psychological": +2, "subjectivity": +0.1},
    "绝望":   {"prose_style_override": "白描", "psychological": -1, "subjectivity": -0.1},
    "压抑":   {"prose_style_override": "紧凑", "psychological": -1, "subjectivity": -0.1},
    "轻松":   {"prose_style_override": "散文式", "psychological": +2, "subjectivity": +0.2},
    "热血":   {"prose_style_override": "紧凑", "psychological": +1, "specificity": +0.1},
    "温情":   {"psychological": +3, "subjectivity": +0.2},
    "黑暗":   {"prose_style_override": "白描", "psychological": -1, "subjectivity": -0.2},
}

# genre tag → limits 调整 (字数范围)
GENRE_LIMITS_MAP: Dict[str, Dict[str, int]] = {
    "短篇":   {"min_chapter_words": 1500, "max_chapter_words": 2500},
    "中篇":   {"min_chapter_words": 2500, "max_chapter_words": 4000},
    "长篇":   {"min_chapter_words": 3000, "max_chapter_words": 5000},
    "史诗":   {"min_chapter_words": 4000, "max_chapter_words": 6000},
    "快节奏": {"min_chapter_words": 1500, "max_chapter_words": 2500},
}

# 默认 fallback
DEFAULT_PROSE_STYLE = "紧凑"
DEFAULT_SENTENCE_LENGTH = "中等"
DEFAULT_PARAGRAPH_STYLE = "白描"
DEFAULT_PSYCHOLOGICAL = 2
DEFAULT_SUBJECTIVITY = 0.5
DEFAULT_SPECIFICITY = 0.7
DEFAULT_LIMITS = {"min_chapter_words": 2500, "max_chapter_words": 3000}


def infer_style_charter(
    genres: List[str],
    styles: List[str],
    tone: List[str],
) -> Dict[str, Any]:
    """根据用户填的 genres/styles/tone 推断完整 style_charter

    Args:
        genres: 题材数组 (如 ["赛博朋克", "末世"])
        styles: 风格数组 (如 ["治愈", "唯美"])
        tone:   基调数组 (如 ["乐观"])

    Returns:
        完整 style_charter dict:
        {
            "prose_style": {"primary": "散文式"},
            "tone": {"primary": "乐观", "psychological_per_paragraph": 5, ...},
            "density": {"specificity": 0.7, "subjectivity": 0.8, ...},
            "limits": {"min_chapter_words": 2500, "max_chapter_words": 3000, ...},
            "metadata": {"inferred_from": ["治愈", "唯美", "乐观"]}
        }
    """
    inferred_from = list(styles) + list(tone) + list(genres)

    # 1. 收集 styles 的笔法参数 (取每项的 max, 这样多个 style 叠加)
    prose_style = DEFAULT_PROSE_STYLE
    sentence_length = DEFAULT_SENTENCE_LENGTH
    paragraph_style = DEFAULT_PARAGRAPH_STYLE
    psychological = DEFAULT_PSYCHOLOGICAL
    subjectivity = DEFAULT_SUBJECTIVITY
    specificity = DEFAULT_SPECIFICITY

    for style in styles:
        params = STYLE_PARAM_MAP.get(style)
        if not params:
            continue
        # 散文系叠加: 优先级散文式 > 紧凑
        # 简单做法: 后注册的覆盖, 但散文系之间不互斥 (取 max)
        if params["prose_style"] == "散文式" and prose_style != "散文式":
            prose_style = "散文式"
        elif params["prose_style"] == "紧凑" and prose_style == DEFAULT_PROSE_STYLE:
            prose_style = "紧凑"
        # sentence_length / paragraph_style: 后注册覆盖 (用户填的顺序)
        if "sentence_length" in params:
            sentence_length = params["sentence_length"]
        if "paragraph_style" in params:
            paragraph_style = params["paragraph_style"]
        # 数值类取 max (叠加效果)
        psychological = max(psychological, params.get("psychological", DEFAULT_PSYCHOLOGICAL))
        subjectivity = max(subjectivity, params.get("subjectivity", DEFAULT_SUBJECTIVITY))
        specificity = max(specificity, params.get("specificity", DEFAULT_SPECIFICITY))

    # 2. 应用 tone 调整
    primary_tone = tone[0] if tone else "冷叙述"
    for t in tone:
        adj = TONE_ADJUST_MAP.get(t)
        if not adj:
            continue
        if "prose_style_override" in adj:
            prose_style = adj["prose_style_override"]
        psychological = max(1, psychological + adj.get("psychological", 0))
        subjectivity = max(0.0, min(1.0, subjectivity + adj.get("subjectivity", 0)))
        specificity = max(0.0, min(1.0, specificity + adj.get("specificity", 0)))

    # 3. 应用 genre 的 limits
    limits = dict(DEFAULT_LIMITS)
    for g in genres:
        gl = GENRE_LIMITS_MAP.get(g)
        if gl:
            limits.update(gl)
            break  # 只取第一个匹配的 genre

    # 4. 组装完整 style_charter (v0.4.1 字段: prose_style / tone / density / taboos / notes / limits)
    return {
        "prose_style": {
            "primary": prose_style,
            "sentence_length": sentence_length,
            "paragraph_style": paragraph_style,
        },
        "tone": {
            "primary": primary_tone,
            "psychological_per_paragraph": psychological,
        },
        "density": {
            "specificity": round(specificity, 2),
            "subjectivity": round(subjectivity, 2),
            "density": 0.5,
            "genre_resonance": 0.8,
            "max_specific_granules_per_kchars": 3,
        },
        "taboos": [],  # v0.7 砍掉了用户填禁区
        "notes": list(styles),  # Step 1 填的 styles 作为笔记
        "limits": {
            "min_chapter_words": limits["min_chapter_words"],
            "max_chapter_words": limits["max_chapter_words"],
            "psychological_per_paragraph": psychological,
            "specific_granules_per_kchars": 3,
        },
        "metadata": {
            "inferred_from": inferred_from,
            "inference_version": "v0.8.2",
        },
    }


# ============ 单元测试用 ============

if __name__ == "__main__":
    # 测试用例
    cases = [
        (["赛博朋克"], ["冷峻"], ["绝望"], "硬科幻冷峻风"),
        (["都市"], ["治愈", "唯美"], ["乐观"], "温暖都市"),
        (["奇幻"], ["史诗"], ["热血"], "史诗热血"),
        ([], [], [], "默认 fallback"),
    ]
    for genres, styles, tone, desc in cases:
        result = infer_style_charter(genres, styles, tone)
        print(f"=== {desc} ===")
        print(f"  prose_style: {result['prose_style']}")
        print(f"  tone: {result['tone']}")
        print(f"  limits: {result['limits']}")
        print()
