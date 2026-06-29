"""core — 核心数据模型与领域对象

不依赖外部服务（LLM/IO/CLI），只定义产品领域内的"概念"和"数据"。
包括:
- schemas/  7 件产物 Pydantic Schema + ChapterSummary
- world_tree.py  S2 WorldTree 内存模型（纯内存操作，无 IO）
- exceptions.py  异常层级（M-α 阶段用最少集合）
- event_bus.py   全局 asyncio 事件总线（零第三方依赖）

v0.8.2: 删除了 project.py (v0.3 同步版 ProjectManager, 0 真调用)
        删除了 SCHEMA_REGISTRY (v0.3 文件存储时代用, v0.4.1 入库后已不适用)
        项目管理走 services.ProjectManager
"""
from . import exceptions
from .event_bus import event_bus
from .schemas import (
    WorldTreeSchema,
    GenreResonanceSchema,
    MainPlotSchema,
    SubPlotSchema,
    CharacterCardSchema,
    SeedTableSchema,
    ChapterSummarySchema,
)
from .world_tree import WorldTree

__all__ = [
    "WorldTree",
    "event_bus",
    "WorldTreeSchema",
    "GenreResonanceSchema",
    "MainPlotSchema",
    "SubPlotSchema",
    "CharacterCardSchema",
    "SeedTableSchema",
    "ChapterSummarySchema",
    "exceptions",
]
