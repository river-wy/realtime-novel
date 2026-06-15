"""core — 核心数据模型与领域对象

不依赖外部服务（LLM/IO/CLI），只定义产品领域内的"概念"和"数据"。
包括:
- schemas/  7 件产物 Pydantic Schema + ChapterSummary
- world_tree.py  S2 WorldTree 内存模型
- project.py  S1 ProjectManager (项目目录 + 文件加载)
- exceptions.py  异常层级（M-α 阶段用最少集合）
"""
from .world_tree import WorldTree
from .project import ProjectManager, Project, LoadedProject
from .schemas import (
    WorldTreeSchema,
    StyleCharterSchema,
    GenreResonanceSchema,
    MainPlotSchema,
    SubPlotSchema,
    CharacterCardSchema,
    SeedTableSchema,
    ChapterSummarySchema,
    SCHEMA_REGISTRY,
)
from . import exceptions

__all__ = [
    "WorldTree",
    "ProjectManager",
    "Project",
    "LoadedProject",
    "WorldTreeSchema",
    "StyleCharterSchema",
    "GenreResonanceSchema",
    "MainPlotSchema",
    "SubPlotSchema",
    "CharacterCardSchema",
    "SeedTableSchema",
    "ChapterSummarySchema",
    "SCHEMA_REGISTRY",
    "exceptions",
]
