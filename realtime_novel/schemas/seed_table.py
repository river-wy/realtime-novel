"""SeedTable Schema — docs/design/03-schemas.md §2.4

跨章复现的颗粒，按 4 维权重排序注入 prompt
"""
from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field, ConfigDict


class SeedTableSchema(BaseModel):
    """03 §2.4 — 7 件之 #7（程序管理）
    文件名约定: 07-seed-table.yaml
    """
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    seeds: List[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
