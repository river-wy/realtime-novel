"""backend · 产品代码包

v0.8.2 重大变更：清理 v0.3 死代码
- services/onboarding.py 删除（v0.3 S3 5 步 CLI 流程）→ 走 v0.5 AsyncOnboardingFlow
- services/intervention.py 删除（v0.3 S5 导演/演员模式）→ 走 v0.6 AsyncInterventionParser
- services/rollback.py 删除（v0.3 S5 落盘式硬 reset）→ v0.4.1 入库后已不适用
- core/project.py 删除（v0.3 S1 ProjectManager 同步版）→ 走 v0.6 AsyncProjectManager
- core.schemas SCHEMA_REGISTRY 删除（v0.3 文件存储时代用）→ 走 project_repository

v0.4+ 架构：
- S1 AsyncProjectManager: 项目管理 (services/async_wrappers.py, 走 DB)
- S2 WorldTree: 7 件产物内存模型 + 序列化 (core/world_tree.py, 纯内存)
- S3 AsyncOnboardingFlow: 5 步启动链路 (services/async_wrappers.py)
- S4 章节生成: 迁到 backend.agent.specialists.generate_chapter_via_specialist（v0.6.1 从 state_graph_stub 归一）
- S5 AsyncInterventionParser + AsyncRollbackManager (services/async_wrappers.py)

schemas/: 7 件 Pydantic Schema（v0.5 全部走 DB）

路线图: docs/roadmap/
设计文档: docs/design/
约束规则: .realtime-novel/conventions.md
"""
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
)
from .utils.version import __version__

__all__ = [
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
]
