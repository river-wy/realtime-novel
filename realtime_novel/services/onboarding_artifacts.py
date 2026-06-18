"""v0.7 onboarding_artifacts — 7 件基座拼装 helper

m-v0.5-onboarding s2 自检后重构 (2026-06-18 22:11):
- 自检发现 Step 3-4 走 WS 后, HTTP step=4 的 7 件拼装逻辑变成死代码
- 3 件 (world_tree / genre_resonance / style_charter 完整结构) 写不出来
- 修复: 把 7 件拼装逻辑抽到独立模块, HTTP 和 WS 都能调

设计原则:
- stateless helper: 输入 project_id + state_json.payload, 调 save_7_artifacts
- save_7_artifacts 是合并式写入 (不丢已有数据)
- WS 和 HTTP 都能复用 (HTTP 兜底, WS 主用)

链路:
  Step 1-2 HTTP: 落 state_json.payload + projects.palette
  Step 3 WS confirm: _write_onboarding_to_artifacts Step 3 分支 (写部分字段) + merge state_json.payload
  Step 4 WS confirm: _write_onboarding_to_artifacts Step 4 分支 → 调 assemble_7_artifacts (完整 7 件拼装)
  Step 5 HTTP: 读 7 件 → 调 LLM 生成第 1 章
"""
from __future__ import annotations

import json
from typing import Dict, Any, List

from realtime_novel.persistence import get_store, ProjectRepository


# ============ 字段映射常量 ============

# 题材 → 时代 (era 推断)
ERA_MAP = {
    "都市": "现代", "校园": "现代", "职场": "现代", "家庭": "现代",
    "科幻": "未来", "赛博朋克": "未来", "末世": "未来",
    "古风": "古代", "武侠": "古代", "仙侠": "古代", "修仙": "古代", "历史": "古代", "军旅": "现代",
    "玄幻": "架空", "奇幻": "架空", "重生": "现代", "穿越": "架空",
    "系统": "架空", "无限流": "架空", "无敌流": "架空", "游戏": "现代",
    "电竞": "现代", "克苏鲁": "现代", "蒸汽朋克": "架空",
    "轻小说": "现代", "二次元": "现代", "异能": "现代", "灵异": "现代", "商战": "现代",
}

# 中文身份 → DB role enum
ROLE_MAP = {
    "主角": "protagonist", "主人公": "protagonist", "女主": "protagonist", "男主": "protagonist",
    "配角": "supporting", "妹妹": "supporting", "弟弟": "supporting", "姐姐": "supporting",
    "哥哥": "supporting",
    "反派": "antagonist", "邪派": "antagonist", "恶人": "antagonist", "魔王": "antagonist",
    "次主角": "deuteragonist", "二主角": "deuteragonist", "盟友": "deuteragonist", "伙伴": "deuteragonist",
    "路人": "minor", "配角1": "minor", "背景": "minor",
}


# ============ 7 件拼装核心 ============

def assemble_7_artifacts(project_id: str, payload: Dict[str, Any]) -> List[str]:
    """从 state_json.payload 拼 7 件, 调 save_7_artifacts 合并写入

    Args:
        project_id: 项目 ID
        payload: onboarding_state.state_json.payload (含 Step 1-4 全部字段)

    Returns:
        artifacts_written: 写入了哪些 7 件表 (固定 7 张, 用于前端展示)

    字段映射:
        Step 1: genres / styles / tone → world_tree + style_charter + genre_resonance
        Step 3: core_relationship / emotional_anchor / taboos / ending_preference
                → style_charter (notes/taboos) + main_plot (metadata) + character_card (核心关系)
        Step 4: main_conflict / sub_plots / characters / seeds
                → main_plot (arc_phrase/beats) + sub_plot + character_card + seed_table

    注意:
        - save_7_artifacts 是合并式写入 (不丢已有数据)
        - 不调 LLM, 直接用结构化数据拼 (避免 1-2 分钟耗时)
        - v0.7+: 考虑用 LLM 生成更丰富的 7 件内容
    """
    genres = payload.get("genres", []) or []
    styles = payload.get("styles", []) or []
    tone = payload.get("tone", "冷叙述")
    palette = payload.get("palette", []) or []  # noqa: 暂时不写入 7 件, 仅做参考
    main_conflict = payload.get("main_conflict", "") or ""
    sub_plots_raw = payload.get("sub_plots", "") or ""
    characters_raw = payload.get("characters", "") or ""
    seeds_raw = payload.get("seeds", "") or ""
    core_relationship = payload.get("core_relationship", "") or ""
    emotional_anchor = payload.get("emotional_anchor", "") or ""
    taboos_raw = payload.get("taboos", "") or ""
    ending_preference = payload.get("ending_preference", "") or ""

    # 推断 era 和 theme
    era = "现代"
    for g in genres:
        if g in ERA_MAP:
            era = ERA_MAP[g]
            break
    theme = genres[0] if genres else "都市"

    # 主线：拼 main_conflict + genres + theme (fallback)
    main_arc = main_conflict or f"{theme}题材下主角的成长与命运"

    # core_rules: 从主线 + 核心关系 + 禁区 推断
    core_rules = [
        {"id": "R1", "statement": f"主线：{main_arc}", "enforcement": "hard", "applies_to": "all"},
        {"id": "R2", "statement": f"核心关系：{core_relationship or '主角与各角色的羁绊'}", "enforcement": "soft", "applies_to": "all"},
    ]
    if taboos_raw:
        core_rules.append({"id": "R3", "statement": f"禁区: {taboos_raw}", "enforcement": "hard", "applies_to": "all"})

    # style_charter.notes: 追加"情感锚点"
    notes_list = list(styles) if styles else []
    if emotional_anchor:
        notes_list.append(f"情感锚点: {emotional_anchor}")

    # style_charter.taboos: list of {id, text}
    taboos_list = []
    if taboos_raw:
        taboos_list.append({"id": "T1", "text": taboos_raw, "source": "user_onboarding_step3"})

    # style_charter.prose_style: 根据 styles 推断
    is_literary = any(s in ["治愈", "唯美", "甜文"] for s in styles)
    prose_style = "散文式" if is_literary else "紧凑"

    # main_plot: beats 构造 (默认 3 beat: 开场/冲突/高潮)
    beats = [
        {"id": "beat-1", "sequence": 1, "title": "开场", "description": main_arc[:50], "status": "active", "chapter_range": {"start": 1, "end": 5}},
        {"id": "beat-2", "sequence": 2, "title": "冲突", "description": "主角面对挑战", "status": "pending", "chapter_range": {"start": 6, "end": 15}},
        {"id": "beat-3", "sequence": 3, "title": "高潮", "description": "高潮与转折", "status": "pending", "chapter_range": {"start": 16, "end": 25}},
    ]

    # 支线: 按行拆
    sub_plot_threads = []
    for line in sub_plots_raw.split("\n"):
        line = line.strip()
        if line:
            sub_plot_threads.append({
                "id": f"sub-{len(sub_plot_threads)+1:02d}",
                "title": line[:30],
                "description": line,
                "status": "pending",
                "priority": "side",
            })

    # 人物: 按行拆 "名字-身份-背景"
    characters = []
    for line in characters_raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("-")
        raw_role = parts[1].strip() if len(parts) > 1 else "supporting"
        mapped_role = ROLE_MAP.get(raw_role, "supporting")
        characters.append({
            "id": f"char-{len(characters)+1:03d}",
            "name": parts[0].strip() if parts else f"角色{len(characters)+1}",
            "role": mapped_role,
            "background": parts[2].strip() if len(parts) > 2 else line,
            "traits": [],
        })

    # 核心关系单独建一个人物 (Step 3, v0.7 拍板补: 核心关系也要入 character_card)
    if core_relationship and not characters:
        # 没有 Step 4 人物时, 用核心关系建一个 protagonist
        characters.append({
            "id": "char-000",
            "name": "主角",
            "role": "protagonist",
            "background": core_relationship,
            "traits": [],
        })

    # 种子: 按行拆
    seeds = []
    for i, line in enumerate(seeds_raw.split("\n")):
        line = line.strip()
        if line:
            seeds.append({
                "id": i + 1,
                "content": line,
                "importance": {"primary": "小巧思"},
                "size": "中线",
                "orientation": "氛围营造",
                "weight": 0.5,
                "status": "planted",
            })

    # 写 7 件 (save_7_artifacts 是合并式)
    repo = ProjectRepository()
    repo.save_7_artifacts(
        project_id=project_id,
        world_tree={
            "base": {
                "timeline": {"era": era, "anchor_event": main_arc[:50]},
                "geography": {"primary": f"{theme}题材下的故事舞台"},
                "core_rules": core_rules,
            },
            "branches": [],
            "metadata": {},
        },
        style_charter={
            "prose_style": {"primary": prose_style},
            "tone": {"primary": tone or "冷叙述"},
            "density": {"specificity": 0.7, "subjectivity": 0.6},
            "taboos": taboos_list,
            "notes": notes_list,
            "limits": {"max_chapter_words": 3000},
            # v0.5 拍板: palette **不**写 7 件基座 (只存 projects.palette)
            # 世界树基座只反映内容创作意图, 不反映 UI 偏好
            "metadata": {"genres": genres, "styles": styles},
        },
        genre_resonance={
            "accept": [{"text": g, "weight": 0.8} for g in genres],
            "reject": [],
            "anchors": [{"phrase": s, "sentiment": "positive"} for s in styles[:3]],
            "metadata": {},
        },
        main_plot={
            "current_beat": 0,
            "arc_phrase": main_arc,
            "beats": beats,
            "metadata": {
                "ending_preference": ending_preference,
                "core_relationship": core_relationship,
                "emotional_anchor": emotional_anchor,
            },
        },
        sub_plot={"threads": sub_plot_threads, "metadata": {}},
        character_card={"characters": characters, "relationships": []},
        seed_table={"seeds": seeds, "metadata": {}},
    )

    return [
        "world_tree",
        "style_charter",
        "genre_resonance",
        "main_plot",
        "sub_plot",
        "character_card",
        "seed_table",
    ]


# ============ 工具函数 ============

def merge_payload_to_state(project_id: str, step: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """把 WS confirm 的 4 字段合并到 onboarding_state.state_json.payload

    Args:
        project_id: 项目 ID
        step: 3 or 4
        fields: 4 字段 dict (来自用户确认)

    Returns:
        merged_payload: 合并后的完整 payload

    注意:
        - 合并而非覆盖 (Step 3 字段保留, Step 4 字段追加)
        - 用同一个 connection 保证原子性
    """
    import json
    from datetime import datetime

    now = datetime.now()
    with get_store().connection() as conn:
        row = conn.execute(
            "SELECT state_json FROM onboarding_state WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"onboarding state not found for project: {project_id}")
        state_data = json.loads(row["state_json"])
        existing_payload = state_data.get("payload", {}) or {}
        # 合并 (新字段覆盖旧字段, 旧字段保留)
        merged = {**existing_payload, **fields}
        state_data["payload"] = merged
        state_data["updated_at"] = now.isoformat()
        conn.execute(
            "UPDATE onboarding_state SET state_json = ?, updated_at = ? WHERE project_id = ?",
            (json.dumps(state_data, ensure_ascii=False), now, project_id),
        )
    return merged


def load_payload(project_id: str) -> Dict[str, Any]:
    """从 onboarding_state.state_json 读完整 payload (Step 1-4 合并)"""
    with get_store().connection() as conn:
        row = conn.execute(
            "SELECT state_json FROM onboarding_state WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    if not row:
        return {}
    state_data = json.loads(row["state_json"])
    return state_data.get("payload", {}) or {}