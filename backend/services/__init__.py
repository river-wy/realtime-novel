"""services — 业务服务层

模块说明（v0.6.1 更新）:
- project_manager.py        项目 CRUD / 软删除 / 回档 / trash 恢复
- onboarding_flow.py        5 步启动链路状态机（DB onboarding_state 表）
- intervention_parser.py    剧情干预写入
- cover_image_generator.py  封面图生成
- onboarding_artifacts.py   7 件基座拼装（Step 4 落库用）
- 章节生成 v0.6.2: 委托文笔家 ReAct loop 走 generate_chapter / summarize_chapter 工具
"""
from .intervention_parser import InterventionParser
from .onboarding_artifacts import assemble_7_artifacts
from .onboarding_flow import OnboardingFlow
from .project_manager import ProjectManager

__all__ = [
    "assemble_7_artifacts",
    "ProjectManager",
    "OnboardingFlow",
    "InterventionParser",
]
