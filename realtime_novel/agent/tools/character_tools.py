"""character_tools.py — introspect_character 工具

v0.6 重构：从 v0_4_new_tools.py 拆出
v0.4 原版 broken：读 world_tree.characters（v0.4.1 后 characters 移到 06-character-card.yaml）
v0.6 修复：走 ProjectRepository.load_all_artifacts 读 character_card
"""
from __future__ import annotations

from realtime_novel.agent.tools.base import BaseTool, ToolError, register_tool
from realtime_novel.agent.tools.schemas import (
    IntrospectCharacterInput, IntrospectResult,
)
from realtime_novel.persistence import ProjectRepository


class IntrospectCharacterTool(BaseTool):
    """角色内省（从 character_card 读角色卡 + 内心独白）

    v0.6 实现：走 DB 读 character_card
    """
    name = "introspect_character"
    description = "角色内省（从 character_card 读角色卡 + 内心独白）"
    input_schema = IntrospectCharacterInput
    output_schema = IntrospectResult

    def __init__(self):
        self._project_repo = ProjectRepository()

    async def run(
        self, input: IntrospectCharacterInput, progress_callback=None
    ) -> IntrospectResult:
        try:
            all_data = self._project_repo.load_all_artifacts(input.project_id)
            character_card = all_data.get("character_card", {})
            characters = character_card.get("characters", []) if isinstance(character_card, dict) else []

            target = next(
                (c for c in characters if c.get("name") == input.character_name),
                None,
            )
            if target is None:
                return ToolError(
                    code="CHARACTER_NOT_FOUND",
                    message=f"Character not found: {input.character_name}",
                )

            # 内心独白：从 arc + background 推断（v0.6 简化版，v0.6.1 可调 LLM 生成）
            inner_monologue = (
                f"我是 {input.character_name}。"
                f"我的背景是：{target.get('background', '未知')}。"
                f"我的弧光是：{target.get('arc', '未知')}。"
                f"我当前的目标是：{target.get('goal', target.get('arc', '未知'))}。"
            )

            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return IntrospectResult(
                character_name=input.character_name,
                character_card=target,
                inner_monologue=inner_monologue,
            )
        except Exception as e:
            return ToolError(code="INTROSPECT_FAILED", message=str(e))


register_tool(IntrospectCharacterTool())
