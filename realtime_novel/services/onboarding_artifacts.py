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
    palette = payload.get("palette", "") or ""  # v0.7: 改为单选 str
    # v0.7 Step 3 (故事引擎) 字段
    story_core = payload.get("story_core", "") or ""
    characters_step3 = payload.get("characters", "") or ""  # Step 3 填的 '名字-要什么-怕什么'
    opening_scene = payload.get("opening_scene", "") or ""
    # v0.7 Step 4 (故事路径) 字段
    main_arc_raw = payload.get("main_arc", "") or ""  # 3-5 节点, 每行 1 个
    sub_plots_raw = payload.get("sub_plots", "") or ""
    seeds_raw = payload.get("seeds", "") or ""
    reader_feeling = payload.get("reader_feeling", "") or ""

    # 推断 era 和 theme
    era = "现代"
    for g in genres:
        if g in ERA_MAP:
            era = ERA_MAP[g]
            break
    theme = genres[0] if genres else "都市"

    # 主线: 用 story_core (Step 3 故事内核) 作为主线信号
    main_arc = story_core or f"{theme}题材下主角的成长与命运"

    # core_rules: 从主线 + 开篇场景 推断 (v0.7: 砍掉禁区/结局偏好)
    core_rules = [
        {"id": "R1", "statement": f"主线: {main_arc}", "enforcement": "hard", "applies_to": "all"},
    ]
    if opening_scene:
        core_rules.append({"id": "R2", "statement": f"开篇场景: {opening_scene}", "enforcement": "soft", "applies_to": "all"})

    # style_charter.notes: 加 styles + 开篇场景
    notes_list = list(styles) if styles else []
    if opening_scene:
        notes_list.append(f"开篇场景: {opening_scene}")

    # style_charter: v0.8.2 由 Agent 推断完整笔法 (散文/句式/段落/心理活动 密度)
    # 不暴露给用户, 用户只填 genres/styles/tone
    from realtime_novel.agent.style_inference import infer_style_charter
    inferred_style_charter = infer_style_charter(
        genres=genres,
        styles=styles,
        tone=tone if isinstance(tone, list) else ([tone] if tone else []),
    )

    # main_plot: beats 构造 (v0.7: 用 main_arc_raw 按行拆, 取代原来固定 3 beat)
    beats = []
    if main_arc_raw:
        for i, line in enumerate(main_arc_raw.split("\n")):
            line = line.strip()
            if not line:
                continue
            beats.append({
                "id": f"beat-{i+1}",
                "sequence": i + 1,
                "title": f"主线节点 {i+1}",
                "description": line[:80],
                "status": "active" if i == 0 else "pending",
                "chapter_range": {"start": i * 5 + 1, "end": (i + 1) * 5},
            })
    else:
        # fallback: 固定 3 beat
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

    # 人物: Step 3 填的 '名字-要什么-怕什么' (取代原 Step 4 '名字-身份-背景')
    characters = []
    for line in characters_step3.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("-")
        name = parts[0].strip() if parts else f"角色{len(characters)+1}"
        want = parts[1].strip() if len(parts) > 1 else ""
        fear = parts[2].strip() if len(parts) > 2 else ""
        # 第一个角色通常是主角
        role = "protagonist" if not characters else "supporting"
        # background 合并 want + fear
        background = f"想要: {want} | 害怕: {fear}" if want or fear else line
        characters.append({
            "id": f"char-{len(characters)+1:03d}",
            "name": name,
            "role": role,
            "background": background,
            "traits": [],
        })

    # story_core 兜底: 如果没有 Step 3 角色但有 story_core, 建一个主角
    if not characters and story_core:
        characters.append({
            "id": "char-000",
            "name": "主角",
            "role": "protagonist",
            "background": story_core,
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
            "metadata": {
                # v0.7: 开篇场景存到世界树 metadata
                "opening_scene": opening_scene,
            },
        },
        style_charter={
            **inferred_style_charter,  # v0.8.2: 完整笔法 (散文/句式/段落/密度/limits)
            "taboos": [],  # v0.7: 砍掉禁区
            "notes": notes_list,
            # v0.5 拍板: palette **不**写 7 件基座 (只存 projects.palette)
            "metadata": {
                **inferred_style_charter.get("metadata", {}),  # 推断来源记录
                "genres": genres,
                "styles": styles,
                "tone": tone if isinstance(tone, list) else [tone] if tone else [],
                # v0.7: reader_feeling 存到 style_charter.metadata
                "reader_feeling": reader_feeling,
            },
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
                # v0.7: 砍掉 ending_preference, 加 story_core 和 reader_feeling
                "story_core": story_core,
                "reader_feeling": reader_feeling,
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