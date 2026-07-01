"""services — 业务服务层

v0.8 变更（2026-07-01 欧尼酱拍板）：
- 删 onboarding_artifacts.delegate_to_wtm（之前含基座生成机械代码 + 状态机）
- 拆为 3 个状态机函数：mark_wtm_pending / mark_wtm_baseline_ready / mark_wtm_baseline_failed
  —— 单纯做状态切换 + emit 事件
- 基座生成完全交给 WTM.run_initial_baseline_react（v0.8 新增，走 ReAct loop）
- 保留 verify_world_tree_baseline（独立工具，边界清晰：校验 vs 委托）
- onboarding_flow.py 保留：OnboardingFlow.update_project_name_in_state 仍被 hooks 调

v003 重构（spec: .spec/db-refactor/spec.md）：
- 删 assemble_7_artifacts（机械关键词拼装）
- 旧 5 步 OnboardingFlow 状态机已废弃（step/load_state 零调用方，class 整体保留以供 hooks 使用）
- 保留 ProjectManager / InterventionParser / cover_image_generator
"""
from .intervention_parser import InterventionParser
from .onboarding_artifacts import (
    mark_wtm_pending,
    mark_wtm_baseline_ready,
    mark_wtm_baseline_failed,
    verify_world_tree_baseline,
)
from .project_manager import ProjectManager

__all__ = [
    "mark_wtm_pending",
    "mark_wtm_baseline_ready",
    "mark_wtm_baseline_failed",
    "verify_world_tree_baseline",
    "ProjectManager",
    "InterventionParser",
]
