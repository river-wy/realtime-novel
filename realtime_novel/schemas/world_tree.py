"""WorldTree Schema — docs/design/03-schemas.md §1.1

故事地基：时间线、地理、核心规则 + 主线/支线节点树
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class Era(str, Enum):
    MODERN = "现代"
    ANCIENT = "古代"
    FUTURE = "未来"
    FANTASY = "架空"


class Enforcement(str, Enum):
    HARD = "hard"
    SOFT = "soft"


class AppliesTo(str, Enum):
    ALL = "all"
    MAIN = "main"
    SUB = "sub"


class NodeType(str, Enum):
    MAIN = "main"
    SUB = "sub"
    SCENE = "scene"


class NodeStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class Timeline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    era: Era
    year_range: Optional[dict] = None  # {start, end?}
    anchor_event: Optional[str] = None


class Geography(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary: str
    secondary: List[str] = Field(default_factory=list)
    spatial_rules: Optional[List[str]] = None


class CoreRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    statement: str
    enforcement: Enforcement
    applies_to: AppliesTo


class TreeNode(BaseModel):
    """WorldTree 上的一个节点（主线/支线/场景）"""
    model_config = ConfigDict(extra="forbid")
    id: str
    type: NodeType
    title: str
    parent_id: Optional[str] = None
    status: NodeStatus
    children: List[str] = Field(default_factory=list)
    beats: Optional[List[dict]] = None  # 主线节点才有，结构见 MainPlot


class WorldTreeSchema(BaseModel):
    """03 §1.1 — 7 件之 #1
    文件名约定: 01-world-tree.yaml
    """
    model_config = ConfigDict(extra="ignore")  # 兼容 v0.2 旧字段

    schema_version: str = "1.0"
    base: dict = Field(default_factory=dict)  # {timeline, geography, core_rules} — 暂用 dict 兜底
    branches: List[TreeNode] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
