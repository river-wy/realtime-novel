"""EditArtifactTool — v0.4.1 结构化编辑 7 件基座

管家 Agent LLM 解析 user message → 调本工具（add/update/delete）

对应 core.md §B.1
"""
from __future__ import annotations

import uuid
from typing import Optional

from backend.agent.tools.base import BaseTool, register_tool
from backend.agent.tools.schemas import (
    EditArtifactInput, EditArtifactResult,
)
from backend.persistence import ProjectRepository


class EditArtifactTool(BaseTool):
    """结构化增量编辑 7 件基座

    9 个 target × 3 个 operation = 27 种组合，下面分块实现
    """
    name = "edit_artifact"
    description = "结构化编辑 7 件基座（add/update/delete）"

    input_schema = EditArtifactInput
    output_schema = EditArtifactResult

    def __init__(self):
        self._pm = ProjectManager()

    async def run(
        self, input: EditArtifactInput, progress_callback=None
    ) -> EditArtifactResult:
        try:
            if progress_callback:
                await progress_callback({"step": "loading", "percentage": 0})

            handler = {
                "project_name": self._edit_project_name,
                "project_palette": self._edit_project_palette,
                "current_pov": self._edit_current_pov,
                "character": self._edit_character,
                "relationship": self._edit_relationship,
                "core_rule": self._edit_core_rule,
                "timeline": self._edit_timeline,
                "geography": self._edit_geography,
                "seed": self._edit_seed,
                "subplot": self._edit_subplot,
                "beat": self._edit_beat,
            }.get(input.target)

            if handler is None:
                return EditArtifactResult(
                    project_id=input.project_id,
                    target=input.target,
                    operation=input.operation,
                    success=False,
                    error=f"Unknown target: {input.target}",
                )

            result = await handler(input)
            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return result
        except Exception as e:
            return EditArtifactResult(
                project_id=input.project_id,
                target=input.target,
                operation=input.operation,
                identifier=input.identifier,
                success=False,
                error=str(e),
            )

    # ============ Project 元数据 ============

    async def _edit_project_name(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        if input.operation == "update":
            new_name = (input.data or {}).get("name", "")
            if not new_name:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False,
                    error="data.name is required",
                )
            repo.update_name(input.project_id, new_name)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, success=True,
                affected={"new_name": new_name},
            )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False,
            error=f"project_name only supports update (got {input.operation})",
        )

    async def _edit_project_palette(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        if input.operation == "update":
            new_palette = (input.data or {}).get("palette", "")
            if not new_palette:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False,
                    error="data.palette is required",
                )
            repo.update_palette(input.project_id, new_palette)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, success=True,
                affected={"new_palette": new_palette},
            )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False,
            error=f"project_palette only supports update (got {input.operation})",
        )

    async def _edit_current_pov(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        if input.operation == "update":
            new_pov = (input.data or {}).get("character_name")
            repo.update_current_pov(input.project_id, new_pov)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, success=True,
                affected={"new_pov": new_pov},
            )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False,
            error=f"current_pov only supports update (got {input.operation})",
        )

    # ============ Character ============

    async def _edit_character(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        data = input.data or {}

        if input.operation == "add":
            char_id = repo.add_character(input.project_id, data)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=char_id, success=True,
                affected={"char_id": char_id, "name": data.get("name")},
            )

        elif input.operation == "update":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False,
                    error="identifier required for update",
                )
            found = repo.update_character(input.project_id, input.identifier, data)
            if not found:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, identifier=input.identifier, success=False,
                    error=f"character not found: {input.identifier}",
                )
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
                affected={"char_id": input.identifier},
            )

        elif input.operation == "delete":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False,
                    error="identifier required for delete",
                )
            repo.delete_character(input.project_id, input.identifier)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
            )

        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False, error="unknown operation",
        )

    # ============ Relationship ============

    async def _edit_relationship(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        data = input.data or {}

        if input.operation == "add":
            from_id = data.get("from_char")
            to_id = data.get("to_char")
            if not (from_id and to_id):
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False,
                    error="data.from_char and data.to_char required",
                )
            rel_id = repo.add_relationship(input.project_id, data)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=rel_id, success=True,
                affected={"rel_id": rel_id, "from": from_id, "to": to_id},
            )

        elif input.operation == "delete":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False,
                    error="identifier required",
                )
            repo.delete_relationship(input.project_id, input.identifier)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
            )

        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False, error="unsupported operation",
        )

    # ============ Core Rule ============

    async def _edit_core_rule(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        rules = repo.get_core_rules(input.project_id)
        if rules is None:
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, success=False,
                error="world_tree not found",
            )

        if input.operation == "add":
            rule = input.data or {}
            rule["id"] = rule.get("id", f"rule-{uuid.uuid4().hex[:6]}")
            rules.append(rule)
        elif input.operation == "update":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            found = False
            for i, r in enumerate(rules):
                if r.get("id") == input.identifier:
                    rules[i] = {**r, **(input.data or {})}
                    found = True
                    break
            if not found:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, identifier=input.identifier, success=False,
                    error=f"rule not found: {input.identifier}",
                )
        elif input.operation == "delete":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            rules = [r for r in rules if r.get("id") != input.identifier]

        repo.save_core_rules(input.project_id, rules)
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, identifier=input.identifier, success=True,
            affected={"rule_count": len(rules)},
        )

    # ============ Timeline / Geography ============

    async def _edit_timeline(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        found = repo.update_timeline(input.project_id, input.data or {})
        if not found:
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, success=False, error="world_tree not found",
            )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation="update", success=True,
            affected={"era": (input.data or {}).get("era")},
        )

    async def _edit_geography(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        found = repo.update_geography(input.project_id, input.data or {})
        if not found:
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, success=False, error="world_tree not found",
            )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation="update", success=True,
            affected={"primary": (input.data or {}).get("primary")},
        )

    # ============ Seed ============

    async def _edit_seed(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        data = input.data or {}

        if input.operation == "add":
            seed_id = repo.add_seed(input.project_id, data)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=str(seed_id), success=True,
                affected={"seed_id": seed_id},
            )

        elif input.operation == "update":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            found = repo.update_seed(input.project_id, int(input.identifier), data)
            if not found:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, identifier=input.identifier, success=False,
                    error=f"seed not found: {input.identifier}",
                )
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
            )

        elif input.operation == "delete":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            repo.delete_seed(input.project_id, int(input.identifier))
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
            )

        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False, error="unsupported",
        )

    # ============ Subplot ============

    async def _edit_subplot(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        data = input.data or {}

        if input.operation == "add":
            sp_id = repo.add_subplot(input.project_id, data)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=sp_id, success=True,
            )

        elif input.operation == "delete":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            repo.delete_subplot(input.project_id, input.identifier)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
            )

        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False, error="unsupported",
        )

    # ============ Beat ============

    async def _edit_beat(self, input: EditArtifactInput) -> EditArtifactResult:
        """Beat 编辑（main_plot.beats 数组，JSON 形式）"""
        repo = ProjectRepository()
        beats = repo.get_beats(input.project_id)
        if beats is None:
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, success=False, error="main_plot not found",
            )

        if input.operation == "add":
            beat = input.data or {}
            beat["id"] = beat.get("id", f"beat-{uuid.uuid4().hex[:6]}")
            beats.append(beat)
        elif input.operation == "update":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            found = False
            for i, b in enumerate(beats):
                if b.get("id") == input.identifier:
                    beats[i] = {**b, **(input.data or {})}
                    found = True
                    break
            if not found:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, identifier=input.identifier, success=False,
                    error="beat not found",
                )
        elif input.operation == "delete":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            beats = [b for b in beats if b.get("id") != input.identifier]

        repo.save_beats(input.project_id, beats)
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, identifier=input.identifier, success=True,
            affected={"beat_count": len(beats)},
        )


# 补上 ProjectManager import
from backend.services.project_manager import ProjectManager

# 注册
register_tool(EditArtifactTool())
