"""onboarding_artifacts — 7 件基座拼装 helper

stateless helper：输入 project_id + state_json.payload，调 save_7_artifacts 合并写入。

链路：
  管家 ReAct → onboarding_user_confirm 工具（Step 3/4）→ assemble_7_artifacts
"""
from __future__ import annotations

from typing import Dict, Any, List

from backend.persistence import ProjectRepository, OnboardingRepository

# ============ 字段映射常量 ============

# 题材 → 时代（era 推断）
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
    """从 state_json.payload 拼装 7 件基座，调 save_7_artifacts 合并写入。

    Args:
        project_id: 项目 ID
        payload: onboarding_state.state_json.payload（含 Step 1-4 全部字段）

    Returns:
        已写入的 7 件名称列表

    字段映射：
        Step 1: genres / styles / tone → world_tree + genre_resonance
        Step 3: story_core / characters / opening_scene → world_tree（core_rules）+ character_card + main_plot（arc_phrase）
        Step 4: main_arc / sub_plots / seeds → main_plot（beats）+ sub_plot + seed_table

    笔风由 projects.style_pack_id 承载，不写入 7 件。
    """
    genres = payload.get("genres", []) or []
    styles = payload.get("styles", []) or []
    tone = payload.get("tone", "冷叙述")
    # Step 3 字段
    story_core = payload.get("story_core", "") or ""
    characters_step3 = payload.get("characters", "") or ""
    opening_scene = payload.get("opening_scene", "") or ""
    # Step 4 字段
    main_arc_raw = payload.get("main_arc", "") or ""
    sub_plots_raw = payload.get("sub_plots", "") or ""
    seeds_raw = payload.get("seeds", "") or ""

    # 推断 era 和 theme
    era = "现代"
    for g in genres:
        if g in ERA_MAP:
            era = ERA_MAP[g]
            break
    theme = genres[0] if genres else "都市"

    # 主线核心：用 story_core 作为主线信号
    main_arc = story_core or f"{theme}题材下主角的成长与命运"

    # core_rules：从主线 + 开篇场景推断
    core_rules = [
        {"id": "R1", "statement": f"主线: {main_arc}", "enforcement": "hard", "applies_to": "all"},
    ]
    if opening_scene:
        core_rules.append({"id": "R2", "statement": f"开篇场景: {opening_scene}", "enforcement": "soft", "applies_to": "all"})

    # main_plot beats：从 main_arc_raw 按行拆
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
        beats = [
            {"id": "beat-1", "sequence": 1, "title": "开场", "description": main_arc[:50], "status": "active", "chapter_range": {"start": 1, "end": 5}},
            {"id": "beat-2", "sequence": 2, "title": "冲突", "description": "主角面对挑战", "status": "pending", "chapter_range": {"start": 6, "end": 15}},
            {"id": "beat-3", "sequence": 3, "title": "高潮", "description": "高潮与转折", "status": "pending", "chapter_range": {"start": 16, "end": 25}},
        ]

    # sub_plot threads：按行拆
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

    # character_card：Step 3 的 '名字 - 身份/角色 - 特点/目的' 格式
    characters = []
    for line in characters_step3.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("-")]
        name = parts[0] if parts and parts[0] else f"角色{len(characters)+1}"
        identity = parts[1] if len(parts) > 1 else ""
        trait = parts[2] if len(parts) > 2 else ""
        role = "protagonist" if not characters else "supporting"
        background = f"身份: {identity} | 特点/目的: {trait}" if identity or trait else line
        characters.append({
            "id": f"char-{len(characters)+1:03d}",
            "name": name,
            "role": role,
            "background": background,
            "traits": [],
        })

    # story_core 兜底：没有 Step 3 角色时建一个主角
    if not characters and story_core:
        characters.append({
            "id": "char-000",
            "name": "主角",
            "role": "protagonist",
            "background": story_core,
            "traits": [],
        })

    # seed_table：按行拆
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

    # 写 7 件（save_7_artifacts 是合并式写入）
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
                "opening_scene": opening_scene,
            },
        },
        # style_charter 表结构保留（DB 兼容），传空 dict
        style_charter={},
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
                "story_core": story_core,
                "main_arc": main_arc_raw,
            },
        },
        sub_plot={"threads": sub_plot_threads, "metadata": {}},
        character_card={"characters": characters, "relationships": []},
        seed_table={"seeds": seeds, "metadata": {}},
    )

    return [
        "world_tree",
        "genre_resonance",
        "main_plot",
        "sub_plot",
        "character_card",
        "seed_table",
    ]


# ============ 工具函数 ============

def merge_payload_to_state(project_id: str, step: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """把 confirm 的字段合并到 onboarding_state.state_json.payload（合并而非覆盖）"""
    return OnboardingRepository().merge_payload(project_id, step, fields)


def load_payload(project_id: str) -> Dict[str, Any]:
    """从 onboarding_state.state_json 读完整 payload（Step 1-4 合并后）"""
    return OnboardingRepository().get_payload(project_id)
