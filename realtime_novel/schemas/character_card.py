"""CharacterCard Schema — docs/design/03-schemas.md §2.3

角色 + 关系 + 弧光
"""
from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field, ConfigDict


class CharacterCardSchema(BaseModel):
    """03 §2.3 — 7 件之 #5
    文件名约定: 06-character-card.yaml
    """
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    characters: List[dict] = Field(default_factory=list)
    relationships: List[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
