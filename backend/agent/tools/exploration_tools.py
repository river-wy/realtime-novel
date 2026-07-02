"""exploration_tools — 探索度调整工具

管家调这个工具调整：
- 项目级探索度 (projects.exploration_level)
- 用户级默认探索度 (user_preferences.default_exploration_level)

三级覆盖机制 (在 specialists/exploration._resolve_exploration_level):
1. 项目级 (projects.exploration_level) — 最高优先级
2. 用户级 (user_preferences.default_exploration_level)
3. agents.json 硬默认 "standard"

探索度档位:
- conservative: 严守用户输入，不自由发挥
- standard: 平衡（默认）
- wild: 鼓励扩展篇幅，添细节，探索不同方向
"""
from __future__ import annotations

import logging
from typing import Literal, Optional
from pydantic import BaseModel, Field

from backend.agent.tools.base import BaseTool, ToolError, register_tool

log = logging.getLogger(__name__)


# ============ Schemas ============

VALID_LEVELS = ("conservative", "standard", "wild")


class UpdateExplorationLevelInput(BaseModel):
    """更新探索度输入

    - level: 新探索度档位 (conservative/standard/wild)
    - scope: 作用范围
        - "project": 修改 projects.exploration_level (需要 project_id)
        - "user":   修改 user_preferences.default_exploration_level (需要 user_id)
    """
    level: Literal["conservative", "standard", "wild"] = Field(
        ...,
        description="新探索度: conservative (严守) / standard (平衡, 默认) / wild (大胆)",
    )
    scope: Literal["project", "user"] = Field(
        default="project",
        description="作用范围: project (项目级) / user (用户级默认)",
    )
    project_id: Optional[str] = Field(
        default=None,
        description="项目 ID（scope=project 时必填）",
    )
    user_id: Optional[str] = Field(
        default=None,
        description="用户 ID（scope=user 时必填，默认 'default'）",
    )


class UpdateExplorationLevelOutput(BaseModel):
    """更新探索度输出"""
    scope: str
    level: str
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    updated: bool


# ============ Tool ============

class UpdateExplorationLevelTool(BaseTool):
    """更新项目或用户的探索度档位"""
    name = "update_exploration_level"
    description = (
        "调整探索度（conservative/standard/wild）。"
        "scope=project 时修改当前项目的探索度（需要 project_id）；"
        "scope=user 时修改用户级默认探索度（所有项目共用）。"
    )
    input_schema = UpdateExplorationLevelInput
    output_schema = UpdateExplorationLevelOutput

    async def run(
        self, input: UpdateExplorationLevelInput, progress_callback=None,
    ) -> UpdateExplorationLevelOutput:
        try:
            if input.scope == "project":
                if not input.project_id:
                    return ToolError(
                        code="MISSING_PROJECT_ID",
                        message="scope=project 时必须传 project_id",
                    )
                # 调 ProjectRepository.update_exploration_level
                from backend.persistence.project_repository import ProjectRepository
                repo = ProjectRepository()
                repo.update_exploration_level(input.project_id, input.level)
                log.info(
                    "update_exploration_level: project=%s, level=%s",
                    input.project_id, input.level,
                )
                return UpdateExplorationLevelOutput(
                    scope="project",
                    level=input.level,
                    project_id=input.project_id,
                    user_id=None,
                    updated=True,
                )
            elif input.scope == "user":
                user_id = input.user_id or "default"
                # 调 UserPreferenceRepository.set
                from backend.persistence.user_preference_repository import UserPreferenceRepository
                repo = UserPreferenceRepository()
                await repo.set(user_id, "default_exploration_level", input.level)
                log.info(
                    "update_exploration_level: user=%s, level=%s",
                    user_id, input.level,
                )
                return UpdateExplorationLevelOutput(
                    scope="user",
                    level=input.level,
                    project_id=None,
                    user_id=user_id,
                    updated=True,
                )
            else:
                # Literal 已在 schema 校验, 这里只是兜底
                return ToolError(
                    code="INVALID_SCOPE",
                    message=f"scope 必须是 project/user, 收到: {input.scope}",
                )
        except Exception as e:
            log.error(
                "update_exploration_level 失败: scope=%s, level=%s, error=%s",
                input.scope, input.level, e,
                exc_info=True,
            )
            return ToolError(code="UPDATE_FAILED", message=str(e))


# 注册
register_tool(UpdateExplorationLevelTool())