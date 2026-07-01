"""prompts.onboarding — DEPRECATED (v0.7)

废弃原因：
- ONBOARDING_STEP3_PROMPT / ONBOARDING_STEP4_PROMPT 仅被 OnboardingController.consult() 使用。
- OnboardingController 在 v0.7 已整体废弃（由管家 ReAct loop 直接收集替代）。
- step 3 由 WorldTreeManager 内部 prompt 处理；step 4 直接读 DB，无独立 prompt。

保留空导出防止残留 import 报错。
"""
from __future__ import annotations

# DEPRECATED stubs — 防止残留 import 炸栈
ONBOARDING_STEP3_PROMPT: str = ""
ONBOARDING_STEP4_PROMPT: str = ""
