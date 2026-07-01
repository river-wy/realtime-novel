"""onboarding_artifacts：管家 WTM 委托入口

v003 重构（spec §5.8）：
- 不再有固定 5 步装配
- 删 assemble_7_artifacts（机械关键词拼装）
- 新增 delegate_to_wtm：管家收集信息后委托 WTM Agent 输出完整世界树基座
- 新增 verify_world_tree_baseline：管家委托后验证基座完整性

链路（新）：
  管家 ReAct（自由对话）→ 调工具暂存 payload（edit_core_rule / add_world_entry 等）
  → 管家判断信息足够
  → 调 delegate_to_wtm() 委托 WTM Agent 输出完整世界树基座
  → 调 verify_world_tree_baseline() 校验 6 项完整性
  → 失败回退 / 成功告知用户
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional

from backend.persistence import OnboardingRepository, ProjectRepository

# ============ 题材 → 时代（era 推断，保留供管家辅助使用） ============

ERA_MAP = {
    "都市": "现代", "校园": "现代", "职场": "现代", "家庭": "现代",
    "科幻": "未来", "赛博朋克": "未来", "末世": "未来",
    "古风": "古代", "武侠": "古代", "仙侠": "古代", "修仙": "古代", "历史": "古代", "军旅": "现代",
    "玄幻": "架空", "奇幻": "架空", "重生": "现代", "穿越": "架空",
    "系统": "架空", "无限流": "架空", "无敌流": "架空", "游戏": "现代",
    "电竞": "现代", "克苏鲁": "现代", "蒸汽朋克": "架空",
    "轻小说": "现代", "二次元": "现代", "异能": "现代", "灵异": "现代", "商战": "现代",
}


# ============ 管家 WTM 委托入口 ============

async def delegate_to_wtm(
    project_id: str,
    steward_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """管家委托 WTM Agent 输出完整世界树基座（spec §5.8.2）

    Args:
        project_id: 项目 ID
        steward_payload: 管家调工具暂存的信息，包含：
            - story_core_hint: 用户提供的故事核心
            - characters_hint: 提及的角色
            - world_setting_hint: 世界观提示
            - core_rules_hint: 提及的约束
            - style_hint: 风格提示
            - 其他 free-form 字段

    Returns:
        {
            "success": bool,
            "summary": {  # 产出摘要
                "world_tree_set": bool,
                "characters_count": int,
                "main_plot_nodes_count": int,
                "volumes_count": int,
                "world_entries_count": int,
                "timeline_events_count": int,
                "geography_locations_count": int,
                "sub_plots_count": int,
                "seeds_count": int,
            },
            "error": Optional[str],
        }
    """
    # 标记 onboarding_state.info_state = 'wtm_pending'
    onboarding_repo = OnboardingRepository()
    onboarding_repo.set_info_state(project_id, "wtm_pending")

    # 委托 WTM Agent（v003 spec §5.8.4）
    # WTM Agent 负责输出完整世界树基座（9 张表）
    # 包括 world_tree / characters / main_plot / sub_plot / volumes /
    # world_entries / timeline_events / geography_locations + core_rules_json
    from backend.agent.agents.world_tree_manager import (
        generate_full_world_tree_baseline,
    )

    result = await generate_full_world_tree_baseline(
        project_id=project_id,
        steward_payload=steward_payload,
    )

    if not result.get("success"):
        # 失败回退到 collecting
        onboarding_repo.set_info_state(project_id, "collecting")
        return {
            "success": False,
            "summary": {},
            "error": result.get("error", "WTM 生成失败"),
        }

    # 成功：标记 info_state = 'ready'
    onboarding_repo.set_info_state(project_id, "ready")

    # 触发后置钩子（项目名 + 封面图生成）。
    # v003 迁移：原 emit 源是 onboarding_user_confirm step=4（v0.7 旧 5 步工具已删除），
    # 迁移到 delegate_to_wtm 成功路径，语义不变——"世界树基座就绪后生成项目名/封面图"。
    # 事件名保持 'onboarding.step4_confirmed'（hooks.py 订阅者不动）。
    try:
        from backend.core.event_bus import event_bus
        await event_bus.emit("onboarding.step4_confirmed", project_id=project_id, payload=steward_payload)
    except Exception as e:
        # 事件 emit 失败不阻断主流程
        import logging
        logging.getLogger(__name__).warning(
            "delegate_to_wtm: step4_confirmed hook emit failed: %s", e,
        )

    return {
        "success": True,
        "summary": result.get("summary", {}),
        "error": None,
    }


def verify_world_tree_baseline(project_id: str) -> Dict[str, Any]:
    """世界树基座完整性校验（spec §5.6）

    校验 6 项：
    - world_tree.story_core 非空
    - world_tree.genre_tags_json 非空
    - world_tree.core_rules_json 非空
    - characters 至少 1 个 protagonist
    - main_plot 至少 1 个 pending 节点
    - volumes 至少 1 个卷

    Returns:
        {
            "ready": bool,
            "missing_items": list[str],  # 缺失项
            "all_items": list[str],      # 全部校验项
        }
    """
    repo = ProjectRepository()
    missing: List[str] = []
    all_items: List[str] = []

    # 1. world_tree.story_core
    all_items.append("world_tree.story_core")
    wt = repo.get_world_tree(project_id)
    if not wt or not wt.story_core:
        missing.append("world_tree.story_core（故事核心）")

    # 2. world_tree.genre_tags_json
    all_items.append("world_tree.genre_tags_json")
    if not wt or not wt.genre_tags_json:
        missing.append("world_tree.genre_tags_json（题材标签）")

    # 3. world_tree.core_rules_json
    all_items.append("world_tree.core_rules_json")
    if not wt or not wt.core_rules_json:
        missing.append("world_tree.core_rules_json（世界核心规则）")

    # 4. characters 至少 1 个 protagonist
    all_items.append("characters.protagonist")
    characters = repo.list_characters(project_id)
    if not characters:
        missing.append("characters（成员列表）")
    elif not any(c.role == "protagonist" for c in characters):
        missing.append("characters（至少 1 个 protagonist）")

    # 5. main_plot 至少 1 个 pending 节点
    all_items.append("main_plot.pending")
    main_plot_nodes = repo.list_main_plot_nodes(project_id)
    if not main_plot_nodes:
        missing.append("main_plot（主线节点）")
    elif not any(n.status == "pending" for n in main_plot_nodes):
        missing.append("main_plot（至少 1 个 pending 节点）")

    # 6. volumes 至少 1 个
    all_items.append("volumes")
    volumes = repo.list_volumes(project_id)
    if not volumes:
        missing.append("volumes（卷规划）")

    return {
        "ready": len(missing) == 0,
        "missing_items": missing,
        "all_items": all_items,
    }


# ============ 工具函数（保留供 onboarding_state 流程使用） ============

def merge_payload_to_state(project_id: str, step: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """把 confirm 的字段合并到 onboarding_state.payload_json"""
    return OnboardingRepository().merge_payload(project_id, step, fields)


def load_payload(project_id: str) -> Dict[str, Any]:
    """从 onboarding_state.payload_json 读完整 payload"""
    return OnboardingRepository().get_payload(project_id)


def get_onboarding_info_state(project_id: str) -> str:
    """读取 onboarding_state.info_state（spec §5.8.5）"""
    return OnboardingRepository().get_info_state(project_id)
