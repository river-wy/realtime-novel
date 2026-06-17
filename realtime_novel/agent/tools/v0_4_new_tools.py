"""v0.4 新增 4 个工具（adjust_style / switch_pov / introspect_character / weave_plot）

对应 core.md §B.1
"""
from __future__ import annotations

from pathlib import Path
import yaml

from realtime_novel.agent.tools.base import BaseTool, ToolError, register_tool
from realtime_novel.agent.tools.schemas import (
    AdjustStyleInput, AdjustStyleResult,
    SwitchPovInput, SwitchPovResult,
    IntrospectCharacterInput, IntrospectResult,
    WeavePlotInput, WeavePlotResult,
)
from realtime_novel.services.async_wrappers import AsyncProjectManager


# ============ adjust_style ============

class AdjustStyleTool(BaseTool):
    name = "adjust_style"
    description = "调整文风（更新 style_charter）"
    input_schema = AdjustStyleInput
    output_schema = AdjustStyleResult

    def __init__(self):
        self._pm = AsyncProjectManager()

    async def run(
        self, input: AdjustStyleInput, progress_callback=None
    ) -> AdjustStyleResult:
        try:
            yaml_path = Path(f"data/{input.project_id}/7_artifacts.yaml")
            data = {}
            if yaml_path.exists():
                data = yaml.safe_load(yaml_path.read_text()) or {}
            style_charter = data.get("style_charter", {})
            if not isinstance(style_charter, dict):
                style_charter = {"raw": str(style_charter)}
            # 追加 directive 到 notes
            notes = style_charter.get("notes", [])
            if not isinstance(notes, list):
                notes = [str(notes)]
            notes.append(input.style_directive)
            style_charter["notes"] = notes
            data["style_charter"] = style_charter
            yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True))
            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return AdjustStyleResult(
                project_id=input.project_id,
                style_charter_updated=True,
            )
        except Exception as e:
            return ToolError(code="ADJUST_STYLE_FAILED", message=str(e))


# ============ switch_pov ============

class SwitchPovTool(BaseTool):
    name = "switch_pov"
    description = "切换 POV 角色（下一章节开始用新 POV）"
    input_schema = SwitchPovInput
    output_schema = SwitchPovResult

    def __init__(self):
        self._pm = AsyncProjectManager()

    async def run(
        self, input: SwitchPovInput, progress_callback=None
    ) -> SwitchPovResult:
        try:
            yaml_path = Path(f"data/{input.project_id}/7_artifacts.yaml")
            data = {}
            if yaml_path.exists():
                data = yaml.safe_load(yaml_path.read_text()) or {}
            previous_pov = str(data.get("current_pov", ""))
            data["current_pov"] = input.new_pov_character
            yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True))
            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return SwitchPovResult(
                project_id=input.project_id,
                previous_pov=previous_pov,
                new_pov=input.new_pov_character,
            )
        except Exception as e:
            return ToolError(code="SWITCH_POV_FAILED", message=str(e))


# ============ introspect_character ============

class IntrospectCharacterTool(BaseTool):
    name = "introspect_character"
    description = "角色内省（从 world_tree 读角色卡 + 内心独白）"
    input_schema = IntrospectCharacterInput
    output_schema = IntrospectResult

    def __init__(self):
        self._pm = AsyncProjectManager()

    async def run(
        self, input: IntrospectCharacterInput, progress_callback=None
    ) -> IntrospectResult:
        try:
            project = await self._pm.load(input.project_id)
            if project is None:
                return ToolError(code="NOT_FOUND", message=f"Project not found: {input.project_id}")
            characters = (project.get("world_tree") or {}).get("characters", [])
            target = next(
                (c for c in characters if c.get("name") == input.character_name),
                None,
            )
            if target is None:
                return ToolError(
                    code="CHARACTER_NOT_FOUND",
                    message=f"Character not found: {input.character_name}",
                )
            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return IntrospectResult(
                character_name=input.character_name,
                character_card=target,
                inner_monologue=f"我是 {input.character_name}，我现在的目标是：{target.get('goal', '未知')}",
            )
        except Exception as e:
            return ToolError(code="INTROSPECT_FAILED", message=str(e))


# ============ weave_plot ============

class WeavePlotTool(BaseTool):
    name = "weave_plot"
    description = "编排下一段剧情（基于 plot_seed 生成 next_chapter_plan）"
    input_schema = WeavePlotInput
    output_schema = WeavePlotResult

    async def run(
        self, input: WeavePlotInput, progress_callback=None
    ) -> WeavePlotResult:
        try:
            if progress_callback:
                await progress_callback({"step": "weaving", "percentage": 30})
            # 简化版：3 段式 plot（背景/冲突/高潮）
            plan = {
                "seed": input.plot_seed,
                "act_1_setup": f"建立场景：引入 '{input.plot_seed}' 作为本章开端",
                "act_2_conflict": f"冲突：主角面对 '{input.plot_seed}' 的挑战",
                "act_3_climax": f"高潮：主角在 '{input.plot_seed}' 的关键时刻做出选择",
                "next_chapter_hooks": [
                    f"延续 {input.plot_seed} 的影响",
                    "埋下新伏笔",
                ],
            }
            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return WeavePlotResult(next_chapter_plan=plan)
        except Exception as e:
            return ToolError(code="WEAVE_PLOT_FAILED", message=str(e))


# 注册 4 个
register_tool(AdjustStyleTool())
register_tool(SwitchPovTool())
register_tool(IntrospectCharacterTool())
register_tool(WeavePlotTool())
