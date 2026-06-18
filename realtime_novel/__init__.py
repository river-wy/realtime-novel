"""realtime_novel · 产品代码包

v0.6 重大变更：v0.3 路径全删
- services/chapter_generator.py 删除（v0.3 S4）→ 走 v0.4+ state_graph_stub
- adapters/llm.py 删除（v0.3 LLMClient）→ 走 v0.4+ LLMAdapter

v0.4+ 架构：
- S1 ProjectManager: 项目目录管理 (core/project.py)
- S2 WorldTree: 7 件产物内存模型 + 序列化 (core/world_tree.py)
- S3 OnboardingFlow: 5 步启动链路（v0.6 切 LLMAdapter）
- S4 state_graph_stub: 章节生成（v0.5 真实 LLM）
- S5 InterventionParser + RollbackManager

schemas/: 7 件 Pydantic Schema（v0.5 全部走 DB）

路线图: docs/roadmap/
设计文档: docs/design/
约束规则: .realtime-novel/conventions.md
"""
from .core.project import ProjectManager, Project, LoadedProject
from .core.world_tree import WorldTree
from .core.schemas import (
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
from .services.onboarding import OnboardingFlow, OnboardingState
from .services.intervention import InterventionParser, Intervention, InterventionMode
from .services.rollback import RollbackManager, RollbackResult
from .utils.version import __version__

__all__ = [
    # S1 (core)
    "ProjectManager",
    "Project",
    "LoadedProject",
    # S2 (core)
    "WorldTree",
    # S3 (services)
    "OnboardingFlow",
    "OnboardingState",
    # S5 (services)
    "InterventionParser",
    "Intervention",
    "InterventionMode",
    "RollbackManager",
    "RollbackResult",
    # 7 件 Schema + 摘要 Schema (core)
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
