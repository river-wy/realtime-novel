"""services — 业务服务（v0.8.2 精简版）

v0.8.2 删除了 v0.3 时代的 3 个死代码:
- onboarding.py (5 步 CLI 引导, 由 v0.5 AsyncOnboardingFlow 替代)
- intervention.py (导演/演员模式, 由 v0.6 AsyncInterventionParser 替代)
- rollback.py (落盘式硬 reset, v0.4.1 入库后已不适用)

保留:
- async_wrappers.py    异步入口 (ProjectManager/OnboardingFlow/InterventionParser/RollbackManager)
- onboarding_artifacts.py  7 件基座拼装 (Step 4 落库用)
"""
from .onboarding_artifacts import assemble_7_artifacts

__all__ = [
    "assemble_7_artifacts",
]
