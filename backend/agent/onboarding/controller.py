"""onboarding_controller — DEPRECATED (v0.7)

废弃原因：
- OnboardingController.consult(step=1/2) 负责独立 LLM 推演 genres/styles/tone/palette 字段。
  新方案：管家通过 ReAct loop 多轮对话直接收集字段，不再需要这一层独立 LLM 推演。
- OnboardingController.consult(step=3/4) 已在 v0.6.2 被 WorldTreeManager.initialize_world_tree() 替代。

所有调用方已迁移：
- onboarding_tools.py step 1/2 → 直接读 onboarding_state.payload 字段返回
- onboarding_tools.py step 3   → delegate WorldTreeManager.initialize_world_tree()
- onboarding_tools.py step 4   → 读 DB artifacts

本文件保留为空 stub，防止外部 import 炸栈。如确认无残留引用，可整体删除。
"""
from __future__ import annotations

from typing import Optional


# ─── Stub 保留，防止残留 import 报错 ───────────────────────────────────────────


def get_onboarding_controller():  # type: ignore[return]
    """DEPRECATED: 返回 None，调用方应迁移到管家 ReAct loop 自主推演。"""
    raise NotImplementedError(
        "OnboardingController 已废弃（v0.7）。"
        "onboarding step 1/2 字段由管家 ReAct loop 直接收集；"
        "step 3 由 WorldTreeManager.initialize_world_tree() 处理。"
    )
