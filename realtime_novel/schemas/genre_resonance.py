"""GenreResonance Schema — docs/design/03-schemas.md §1.3

用户接受什么 + 拒绝什么（00 v3.1 的"题材共鸣"维度）
"""
from __future__ import annotations

from enum import Enum
from typing import List
from pydantic import BaseModel, Field, ConfigDict


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class Binding(str, Enum):
    HARD = "hard"
    SOFT = "soft"


class Source(str, Enum):
    STEP_1A = "step-1a"
    STEP_1B = "step-1b"
    USER_INPUT = "user-input"


class GenreResonanceSchema(BaseModel):
    """03 §1.3 — 7 件之 #3
    文件名约定: 03-genre-resonance.yaml
    """
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    accept: List[dict] = Field(default_factory=list)
    reject: List[dict] = Field(default_factory=list)
    anchors: List[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
