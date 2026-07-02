"""onboarding_artifacts：WTM 基座状态机 + 完整性校验

改造内容：
- 删 delegate_to_wtm 函数（之前含基座生成机械代码 + 状态机）
- 新增 3 个独立函数：mark_wtm_pending / mark_wtm_baseline_ready / mark_wtm_baseline_failed
  —— 单纯做状态机切换 + emit 事件
- 基座生成完全交给 WTM.run_initial_baseline_react（走 ReAct loop）
- 保留 verify_world_tree_baseline（spec §5.6 6 项校验，管家委托前后调）

链路：
  管家 ReAct → 收集足够 hint → delegate_to_agent(agent=WTM, intent=initial_baseline, payload=...)
    → delegation_tools 调 mark_wtm_pending(info_state=wtm_pending)
    → WTM.run_initial_baseline_react 走 ReAct 自主落库 9 张表
    → 成功 → delegation_tools 调 mark_wtm_baseline_ready(info_state=ready + emit step4_confirmed)
    → 失败 → delegation_tools 调 mark_wtm_baseline_failed(info_state=collecting)
  → 管家收到结果 → 整合回复用户
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional

from backend.persistence import OnboardingRepository, ProjectRepository

# ============ WTM 基座状态机 ============

def mark_wtm_pending(project_id: str) -> None:
    """WTM 委托开始：info_state = 'wtm_pending'

    由 delegation_tools._delegate_wtm_initial_baseline 在调 WTM 前调
    """
    OnboardingRepository().set_info_state(project_id, "wtm_pending")


def mark_wtm_baseline_ready(project_id: str) -> None:
    """WTM 委托成功：info_state = 'ready' + emit onboarding.step4_confirmed 事件

    基座生成在 WTM 内部完成（ReAct），service 层只切状态 + emit
    事件钩子：onboarding_hooks.handle_step4_confirmed → 生成项目名 + 封面图
    """
    OnboardingRepository().set_info_state(project_id, "ready")
    try:
        from backend.core.event_bus import event_bus
        # 同步触发（fire-and-forget），不等待 hooks 完成
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(event_bus.emit("onboarding.step4_confirmed", project_id=project_id))
            else:
                loop.run_until_complete(event_bus.emit("onboarding.step4_confirmed", project_id=project_id))
        except RuntimeError:
            # 没有运行中的 event loop（同步上下文），开新 loop
            asyncio.run(event_bus.emit("onboarding.step4_confirmed", project_id=project_id))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "mark_wtm_baseline_ready: step4_confirmed hook emit failed: %s", e,
        )


def mark_wtm_baseline_failed(project_id: str, error: str) -> None:
    """WTM 委托失败：info_state = 'collecting'（回退，管家继续对话收集）

    失败时回退到 collecting，让管家继续与用户对话
    """
    OnboardingRepository().set_info_state(project_id, "collecting")
    import logging
    logging.getLogger(__name__).warning(
        "WTM initial_baseline FAILED, info_state 回退 collecting: project_id=%s, error=%s",
        project_id, error,
    )


# ============ 完整性校验 ============

def verify_world_tree_baseline(project_id: str) -> Dict[str, Any]:
    """世界树基座完整性校验（spec §5.6 6 项）

    管家委托前后调：委托前看缺什么提示用户，委托后看是否就绪
    WTM.run_initial_baseline_react 完成后管家会调此函数二次确认

    校验 6 项：
    - world_tree.story_core 非空
    - world_tree.genre_tags_json 非空
    - world_tree.core_rules_json 非空
    - characters 至少 1 个 protagonist
    - main_plot 至少 1 个 pending 节点
    - volumes 至少 1 个卷

    Returns:
        {"ready": bool, "missing_items": list[str], "all_items": list[str]}
    """
    repo = ProjectRepository()
    missing: List[str] = []
    all_items: List[str] = []

    all_items.append("world_tree.story_core")
    wt = repo.get_world_tree(project_id)
    if not wt or not wt.story_core:
        missing.append("world_tree.story_core（故事核心）")

    all_items.append("world_tree.genre_tags_json")
    if not wt or not wt.genre_tags_json:
        missing.append("world_tree.genre_tags_json（题材标签）")

    all_items.append("world_tree.core_rules_json")
    if not wt or not wt.core_rules_json:
        missing.append("world_tree.core_rules_json（世界核心规则）")

    all_items.append("characters.protagonist")
    characters = repo.list_characters(project_id)
    if not characters:
        missing.append("characters（成员列表）")
    elif not any(c.role == "protagonist" for c in characters):
        missing.append("characters（至少 1 个 protagonist）")

    all_items.append("main_plot.pending")
    main_plot_nodes = repo.list_main_plot_nodes(project_id)
    if not main_plot_nodes:
        missing.append("main_plot（主线节点）")
    elif not any(n.status == "pending" for n in main_plot_nodes):
        missing.append("main_plot（至少 1 个 pending 节点）")

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
