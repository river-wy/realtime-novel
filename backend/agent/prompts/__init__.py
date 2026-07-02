"""prompts — Prompt 集中

公开 API re-export (保持外部 import 路径不变):
- WORLDTREE_KEEPER_PROMPT
- CHAPTER_GENERATOR_PROMPT
- MEMORY_KEEPER_PROMPT

DEPRECATED 保留导出防止残留 import 报错（值为空串）:
- ONBOARDING_STEP3_PROMPT
- ONBOARDING_STEP4_PROMPT

实现文件:
- specialists: 3 个 specialist prompt (worldtree/chapter/memory)
- onboarding: 保留空 stub
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
