"""services — 业务服务层

模块说明：
- async_project_manager.py    项目 CRUD / 软删除 / 回档 / trash 恢复
- async_chapter_generator.py  章节生成（委托 state_graph_stub）
- async_onboarding_flow.py    5 步启动链路状态机（DB onboarding_state 表）
- async_intervention_parser.py 剧情干预写入
- async_rollback_manager.py   回档委托
- async_wrappers.py           向后兼容转发层（保留旧 import 路径）
- onboarding_artifacts.py     7 件基座拼装（Step 4 落库用）
"""
from .async_chapter_generator import AsyncChapterGenerator
from .async_intervention_parser import AsyncInterventionParser
from .async_onboarding_flow import AsyncOnboardingFlow
from .async_project_manager import AsyncProjectManager
from .async_rollback_manager import AsyncRollbackManager
from .onboarding_artifacts import assemble_7_artifacts

__all__ = [
    "assemble_7_artifacts",
    "AsyncProjectManager",
    "AsyncChapterGenerator",
    "AsyncOnboardingFlow",
    "AsyncInterventionParser",
    "AsyncRollbackManager",
]
