"""realtime_novel · 产品代码包

v0.8.2 重大变更：清理 v0.3 死代码
- services/onboarding.py 删除（v0.3 S3 5 步 CLI 流程）→ 走 v0.5 AsyncOnboardingFlow
- services/intervention.py 删除（v0.3 S5 导演/演员模式）→ 走 v0.6 AsyncInterventionParser
- services/rollback.py 删除（v0.3 S5 落盘式硬 reset）→ v0.4.1 入库后已不适用

v0.4+ 架构：
- S1 ProjectManager: 项目目录管理 (core/project.py)
- S2 WorldTree: 7 件产物内存模型 + 序列化 (core/world_tree.py)
- S3 OnboardingFlow (v0.5+ AsyncOnboardingFlow, 走 DB)
- S4 state_graph_stub: 章节生成（v0.5 真实 LLM）
- S5 InterventionParser + RollbackManager (v0.6+ Async*, 走 DB)

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
from .utils.version import __version__

__all__ = [
    # S1 (core)
    "ProjectManager",
    "Project",
    "LoadedProject",
    # S2 (core)
    "WorldTree",
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
