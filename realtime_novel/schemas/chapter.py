"""ChapterSummary Schema — docs/design/02-consistency.md §4.3

章节级摘要 schema（从 eval/v0.2/pipeline/real_llm.call_llm_extract_summary 抽出）

字段:
- chapter_id: 章节号
- range: 章节范围描述
- key_events: 关键事件列表
- seed_changes: 种子状态变化
  - planted: 本章新埋的种子
  - resonating: 本章强化中的种子
  - harvested: 本章回收的种子
- character_state: 人物状态（动态）
- unresolved: 未解决的悬念
"""
from __future__ import annotations

from typing import List, Dict
from pydantic import BaseModel, Field, ConfigDict


class SeedChanges(BaseModel):
    model_config = ConfigDict(extra="ignore")
    planted: List[int] = Field(default_factory=list)
    resonating: List[int] = Field(default_factory=list)
    harvested: List[int] = Field(default_factory=list)


class ChapterSummarySchema(BaseModel):
    """02 §4.3 — 章节级摘要"""
    model_config = ConfigDict(extra="ignore")

    chapter_id: int
    range: str = ""
    key_events: List[str] = Field(default_factory=list)
    seed_changes: SeedChanges = Field(default_factory=SeedChanges)
    character_state: Dict[str, str] = Field(default_factory=dict)
    unresolved: List[str] = Field(default_factory=list)
