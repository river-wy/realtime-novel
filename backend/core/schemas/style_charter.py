"""StyleCharter Schema — docs/design/03-schemas.md §1.2

写作的 4 维原则 + 硬约束（来自 00 v3.1）
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ProseStyle(str, Enum):
    PROSE = "散文式"
    DIALOGUE = "对话驱动"
    STREAM = "意识流"
    TRADITIONAL = "传统小说"


class SentenceLength(str, Enum):
    SHORT = "短句为主"
    MIXED = "长短交错"
    LONG = "长句为主"


class TabooSeverity(str, Enum):
    FORBIDDEN = "forbidden"
    DISCOURAGED = "discouraged"


class StyleCharterSchema(BaseModel):
    """03 §1.2 — 7 件之 #2
    文件名约定: 02-style-charter.yaml
    """
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    prose_style: dict = Field(default_factory=dict)
    tone: dict = Field(default_factory=dict)
    density: dict = Field(default_factory=dict)
    taboos: List[dict] = Field(default_factory=list)
    limits: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
