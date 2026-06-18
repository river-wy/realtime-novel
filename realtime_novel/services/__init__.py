"""services — 业务服务（S1-S5 orchestrators）

v0.6: chapter_generator.py 已删除（v0.3 S4 章节生成器），改为走 v0.4+ state_graph_stub
- onboarding.py        S3 启动链路 5 步引导（v0.6 切 LLMAdapter）
- intervention.py      S5 干预解析
- rollback.py          S5 回档落盘

未来:
- project_manager.py   S1 项目管理（业务侧，目前在 core/project.py）
- world_tree_service.py  S2 WorldTree 服务层
"""
from .onboarding import OnboardingFlow, OnboardingState
from .intervention import InterventionParser, Intervention, InterventionMode
from .rollback import RollbackManager, RollbackResult

__all__ = [
    "OnboardingFlow",
    "OnboardingState",
    "InterventionParser",
    "Intervention",
    "InterventionMode",
    "RollbackManager",
    "RollbackResult",
]
