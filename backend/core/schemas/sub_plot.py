"""SubPlot Schema — docs/design/03-schemas.md §2.2

支线故事的容器（可挂主线，可独立）
"""
from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field, ConfigDict


class SubPlotSchema(BaseModel):
    """03 §2.2 — 7 件之 #6
    文件名约定: 05-sub-plot.yaml
    """
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    threads: List[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
