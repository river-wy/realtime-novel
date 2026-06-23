"""MainPlot Schema — docs/design/03-schemas.md §2.1

主线的节拍推进
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class TriggerType(str, Enum):
    USER_DECISION = "user-decision"
    AUTO = "auto"
    SEED_DRIVEN = "seed-driven"


class BeatStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"


class MainPlotSchema(BaseModel):
    """03 §2.1 — 7 件之 #4
    文件名约定: 04-main-plot.yaml
    """
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    beats: List[dict] = Field(default_factory=list)
    current_beat: int = 0
    arc_phrase: str = ""
    metadata: dict = Field(default_factory=dict)
