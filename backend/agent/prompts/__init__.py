"""prompts — Prompt 集中（v0.7 清理废弃 onboarding prompt）

公开 API re-export (保持外部 import 路径不变):
- WORLDTREE_KEEPER_PROMPT
- CHAPTER_GENERATOR_PROMPT
- MEMORY_KEEPER_PROMPT

v0.7 废弃：
- ONBOARDING_STEP3_PROMPT / ONBOARDING_STEP4_PROMPT — 仅被 OnboardingController 使用，
  OnboardingController 已整体废弃。保留导出（值为空串）防止残留 import 报错。

实现文件:
- specialists: 3 个 specialist prompt (worldtree/chapter/memory)
- onboarding: DEPRECATED — 保留空 stub
"""
from __future__ import annotations

# DEPRECATED: 保留导出防止残留 import 报错，值为空串
from backend.agent.prompts.onboarding import (
    ONBOARDING_STEP3_PROMPT,
    ONBOARDING_STEP4_PROMPT,
)
from backend.agent.prompts.specialists import (
    WORLDTREE_KEEPER_PROMPT,
    CHAPTER_GENERATOR_PROMPT,
    MEMORY_KEEPER_PROMPT,
)

__all__ = [
    "WORLDTREE_KEEPER_PROMPT",
    "CHAPTER_GENERATOR_PROMPT",
    "MEMORY_KEEPER_PROMPT",
    # DEPRECATED stubs:
    "ONBOARDING_STEP3_PROMPT",
    "ONBOARDING_STEP4_PROMPT",
]
