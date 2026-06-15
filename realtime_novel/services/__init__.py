"""services — 业务服务（S1-S5 orchestrators）

每个文件对应路线图 (docs/roadmap/v0.3-product-skeleton.md) 中的一个 orchestrator:
- chapter_generator.py  S4 章节生成（已实现，M-β）

未来:
- project_manager.py   S1 项目管理（业务侧，目前在 core/project.py）
- world_tree_service.py  S2 WorldTree 服务层（M-α 阶段 core/world_tree.py 已含）
- onboarding.py        S3 启动链路（M-γ）
- intervention.py      S5 干预 + 回档（M-δ）
"""
from .chapter_generator import ChapterGenerator, GenerationResult

__all__ = [
    "ChapterGenerator",
    "GenerationResult",
]
