"""async_wrappers — 向后兼容转发层

所有类已拆分到独立文件，此模块保留是为了不破坏已有 import：
    from realtime_novel.services.async_wrappers import AsyncProjectManager
    from realtime_novel.services.async_wrappers import AsyncOnboardingFlow
    ...

推荐新代码直接从各子模块导入：
    from realtime_novel.services.async_project_manager import AsyncProjectManager
    from realtime_novel.services.async_chapter_generator import AsyncChapterGenerator
    from realtime_novel.services.async_onboarding_flow import AsyncOnboardingFlow
    from realtime_novel.services.async_intervention_parser import AsyncInterventionParser
    from realtime_novel.services.async_rollback_manager import AsyncRollbackManager
"""
from realtime_novel.services.async_chapter_generator import AsyncChapterGenerator
from realtime_novel.services.async_intervention_parser import AsyncInterventionParser
from realtime_novel.services.async_onboarding_flow import AsyncOnboardingFlow, _step_to_num
from realtime_novel.services.async_project_manager import AsyncProjectManager
from realtime_novel.services.async_rollback_manager import AsyncRollbackManager

__all__ = [
    "AsyncProjectManager",
    "AsyncChapterGenerator",
    "AsyncOnboardingFlow",
    "AsyncInterventionParser",
    "AsyncRollbackManager",
    "_step_to_num",
]
