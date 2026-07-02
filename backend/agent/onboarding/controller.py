"""onboarding_controller — DEPRECATED stub

废弃原因：
- step 1/2 字段由管家 ReAct loop 直接收集
- step 3 由 WorldTreeManager.run_initial_baseline_react() 处理
- step 4 直接读 DB artifacts

本文件保留为空 stub，防止外部 import 炸栈。如确认无残留引用，可整体删除。
"""
from __future__ import annotations

from typing import Optional


# ─── Stub 保留，防止残留 import 报错 ───────────────────────────────────────────


def get_onboarding_controller():  # type: ignore[return]
    """DEPRECATED: 返回 None，调用方应迁移到管家 ReAct loop 自主推演。"""
    raise NotImplementedError(
        "OnboardingController 已废弃。"
        "onboarding step 1/2 字段由管家 ReAct loop 直接收集；"
        "step 3 由 WorldTreeManager.run_initial_baseline_react() 处理。"
    )
