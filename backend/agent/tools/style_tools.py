"""style_tools.py — 笔风相关工具

- list_style_packs:  列出所有可用笔风（id/name/tagline），供 agent 选笔风时读取
- adjust_style:      切换项目笔风（写入 projects.style_pack_id）

v0.6.2 重构：从 style_charter 切换为 style_pack（操作 projects.style_pack_id）
v0.6 重构：从 v0_4_new_tools.py 拆出
"""
from __future__ import annotations

import logging
from pydantic import BaseModel, Field
from typing import Any, List

from backend.agent.tools.base import BaseTool, ToolError, register_tool
from backend.agent.tools.schemas import (
    AdjustStyleInput, AdjustStyleResult,
)

log = logging.getLogger(__name__)


# ============ list_style_packs Schemas ============

class ListStylePacksInput(BaseModel):
    """无需参数，直接返回所有笔风摘要列表"""
    pass


class StylePackSummary(BaseModel):
    id: str
    name: str
    tagline: str


class ListStylePacksOutput(BaseModel):
    style_packs: List[StylePackSummary] = Field(
        description="所有可用笔风的摘要列表（id/name/tagline），用于 agent 判断选哪个笔风"
    )
    default_id: str = Field(description="默认笔风 id（无法判断时使用）")


# ============ list_style_packs Tool ============

class ListStylePacksTool(BaseTool):
    """列出所有可用写作笔风

    返回每个笔风的 id / name / tagline，供 agent 对照用户题材/风格/基调做选择。
    选定后通过 adjust_style 工具写入项目。
    """
    name = "list_style_packs"
    description = (
        "列出系统内所有可用写作笔风（id/name/tagline）。"
        "在 Onboarding 或用户要求调整笔风时，先调此工具读取可用列表，"
        "再根据用户题材/风格/基调选择最匹配的 style_pack_id，"
        "最后通过 adjust_style 工具写入项目。"
    )
    input_schema = ListStylePacksInput
    output_schema = ListStylePacksOutput

    async def run(
        self, input: ListStylePacksInput, progress_callback=None
    ) -> ListStylePacksOutput:
        try:
            from backend.agent.prompts.style_packs import list_style_packs, get_default_pack_id

            packs_raw = list_style_packs()
            packs = [StylePackSummary(**p) for p in packs_raw]
            default_id = get_default_pack_id()

            log.debug("list_style_packs: 返回 %d 个笔风，默认=%s", len(packs), default_id)
            return ListStylePacksOutput(style_packs=packs, default_id=default_id)
        except Exception as e:
            log.error("list_style_packs 失败: %s", e, exc_info=True)
            return ToolError(code="LIST_STYLE_PACKS_FAILED", message=str(e))


# ============ adjust_style Tool ============

class AdjustStyleTool(BaseTool):
    """切换写作笔风（更新项目的 style_pack_id）"""
    name = "adjust_style"
    description = (
        "切换写作笔风（更新项目的 style_pack_id）。"
        "调用前请先通过 list_style_packs 获取可用笔风列表，再传入选定的 style_pack_id。"
    )
    input_schema = AdjustStyleInput
    output_schema = AdjustStyleResult

    async def run(
        self, input: AdjustStyleInput, progress_callback=None
    ) -> AdjustStyleResult:
        try:
            from backend.persistence import ProjectRepository

            repo = ProjectRepository()
            repo.update_style_pack_id(input.project_id, input.style_pack_id)

            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return AdjustStyleResult(
                project_id=input.project_id,
                style_pack_updated=True,
            )
        except Exception as e:
            return ToolError(code="ADJUST_STYLE_FAILED", message=str(e))


register_tool(ListStylePacksTool())
register_tool(AdjustStyleTool())
