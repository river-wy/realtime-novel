"""prompts — Prompt 集中（v0.6.1 P4 拆 prompts.py 386 行）

公开 API re-export (保持外部 import 路径不变):
- from backend.agent.prompts.prompts import (
    WORLDTREE_KEEPER_PROMPT,
    CHAPTER_GENERATOR_PROMPT,
    MEMORY_KEEPER_PROMPT,
    ONBOARDING_STEP3_PROMPT,
    ONBOARDING_STEP4_PROMPT,
)

实现文件 (P4 拆分):
- specialists: 3 个 specialist prompt (worldtree/chapter/memory)
- onboarding: Step 3/4 推演 prompt

v0.6.1 删 9 个死 prompt (v0.4 6 节点 StateGraph 时代 + 3 个 summary 旧版):
- INTAKE_PROMPT / CONSULT_EXPERTS_PROMPT / PLAN_PROMPT / ACT_PROMPT / REFLECT_PROMPT / RESPOND_PROMPT
- CHAPTER_SUMMARY_PROMPT / CHAPTER_DETAILED_SUMMARY_PROMPT / CONVERSATION_SUMMARY_PROMPT

无引用方 (grep 验证), 全部 v0.4 残留。
"""
from __future__ import annotations

from backend.agent.prompts.specialists import (
    WORLDTREE_KEEPER_PROMPT,
    CHAPTER_GENERATOR_PROMPT,
    MEMORY_KEEPER_PROMPT,
)
from backend.agent.prompts.onboarding import (
    ONBOARDING_STEP3_PROMPT,
    ONBOARDING_STEP4_PROMPT,
)

__all__ = [
    "WORLDTREE_KEEPER_PROMPT",
    "CHAPTER_GENERATOR_PROMPT",
    "MEMORY_KEEPER_PROMPT",
    "ONBOARDING_STEP3_PROMPT",
    "ONBOARDING_STEP4_PROMPT",
]
