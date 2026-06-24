"""services — 业务服务层

模块说明：
- project_manager.py        项目 CRUD / 软删除 / 回档 / trash 恢复
- chapter_generator.py      章节生成（委托 state_graph_stub）
- onboarding_flow.py        5 步启动链路状态机（DB onboarding_state 表）
- intervention_parser.py    剧情干预写入
- cover_image_generator.py  封面图生成
- onboarding_artifacts.py   7 件基座拼装（Step 4 落库用）
"""
from .chapter_generator import ChapterGenerator
from .intervention_parser import InterventionParser
from .onboarding_artifacts import assemble_7_artifacts
from .onboarding_flow import OnboardingFlow
from .project_manager import ProjectManager

__all__ = [
    "assemble_7_artifacts",
    "ProjectManager",
    "ChapterGenerator",
    "OnboardingFlow",
    "InterventionParser",
]
