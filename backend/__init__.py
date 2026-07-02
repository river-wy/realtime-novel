"""backend · 产品代码包

S1-S5 架构:
- S1 AsyncProjectManager: 项目管理 (services/async_wrappers.py, 走 DB)
- S2 WorldTree: 7 件产物内存模型 + 序列化 (core/world_tree.py, 纯内存)
- S3 AsyncOnboardingFlow: 5 步启动链路 (services/async_wrappers.py)
- S4 章节生成: 委托文笔家 ReAct loop 走 generate_chapter / summarize_chapter 工具
- S5 AsyncInterventionParser + AsyncRollbackManager (services/async_wrappers.py)

schemas/: 7 件 Pydantic Schema（全部走 DB）

路线图: docs/roadmap/
设计文档: docs/design/
约束规则: .realtime-novel/conventions.md
"""
from .core.schemas import (
    WorldTreeSchema,
    GenreResonanceSchema,
    MainPlotSchema,
    SubPlotSchema,
    CharacterCardSchema,
    SeedTableSchema,
    ChapterSummarySchema,
)
from .core.world_tree import WorldTree
from .utils.version import __version__

__all__ = [
    # S2 (core)
    "WorldTree",
    # 7 件 Schema + 摘要 Schema (core)
    "WorldTreeSchema",
    "GenreResonanceSchema",
    "MainPlotSchema",
    "SubPlotSchema",
    "CharacterCardSchema",
    "SeedTableSchema",
    "ChapterSummarySchema",
]
