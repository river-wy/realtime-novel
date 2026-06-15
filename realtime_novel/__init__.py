"""realtime_novel · 产品代码包

M-α 阶段产出（v0.3-product-skeleton.md §4）:
- S1 ProjectManager: 项目目录管理
- S2 WorldTree: 7 件产物内存模型 + 序列化
- schemas/: 7 件 Pydantic Schema

后续里程碑:
- M-β: S4 ChapterGenerator（接 LLM）
- M-γ: S3 OnboardingFlow（CLI 启动链路）
- M-δ: S5 InterventionParser + RollbackManager

路线图: docs/roadmap/v0.3-product-skeleton.md
设计文档: docs/design/03-schemas.md
约束规则: .realtime-novel/conventions.md
"""
from .project import ProjectManager, Project, LoadedProject
from .world_tree import WorldTree
from .chapter_generator import ChapterGenerator, GenerationResult
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

__version__ = "0.2.0-beta"

__all__ = [
    # S1
    "ProjectManager",
    "Project",
    "LoadedProject",
    # S2
    "WorldTree",
    # S4 (M-β 新增)
    "ChapterGenerator",
    "GenerationResult",
    # 7 件 Schema + 摘要 Schema
    "WorldTreeSchema",
    "StyleCharterSchema",
    "GenreResonanceSchema",
    "MainPlotSchema",
    "SubPlotSchema",
    "CharacterCardSchema",
    "SeedTableSchema",
    "ChapterSummarySchema",
    "SCHEMA_REGISTRY",
]
