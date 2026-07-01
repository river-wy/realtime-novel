"""EditArtifactTool：结构化编辑 6 件基座（add/update/delete）"""
from __future__ import annotations

import uuid
from typing import Optional

from backend.agent.tools.base import BaseTool, register_tool
from backend.agent.tools.schemas import (
    EditArtifactInput, EditArtifactResult,
)
from backend.persistence import ProjectRepository


class EditArtifactTool(BaseTool):
    """结构化增量编辑 6 件基座

    9 个 target × 3 个 operation = 27 种组合
    """
    name = "edit_artifact"
    description = "结构化编辑 6 件基座（add/update/delete）"

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
                "current_pov": self._edit_current_pov,
                "character": self._edit_character,
                "relationship": self._edit_relationship,
                "core_rule": self._edit_core_rule,
                "timeline_event": self._edit_timeline_event,
                "geography_location": self._edit_geography_location,
                "world_entry": self._edit_world_entry,
                "seed": self._edit_seed,
                "subplot": self._edit_subplot,
                "main_plot_node": self._edit_main_plot_node,
                "volume": self._edit_volume,
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

    async def _edit_current_pov(self, input: EditArtifactInput) -> EditArtifactResult:
        """current_pov 存 char_id，写入前校验角色存在"""
        repo = ProjectRepository()
        if input.operation == "update":
            char_id = (input.data or {}).get("char_id")
            if not char_id:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False,
                    error="data.char_id 是必填字段（格式: char-xxxxxxxx）",
                )
            char = repo.get_character(input.project_id, char_id)
            if char is None:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False,
                    error=f"角色 {char_id} 不存在，请先用 edit_artifact(target=character, operation=add) 创建",
                )
            # v003：current_pov 迁入 project_state
            repo.upsert_project_state(input.project_id, current_pov=char_id)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, success=True,
                affected={"new_pov_char_id": char_id, "new_pov_name": char.name if char else ""},
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

    # ============ Timeline / Geography / WorldEntry（v003 拆为事件/地点级）============
    # ============ WorldEntry（v003 新增）============
    async def _edit_world_entry(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        data = input.data or {}

        if input.operation == "add":
            entry_id = repo.add_world_entry(input.project_id, data)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=entry_id, success=True,
                affected={"entry_id": entry_id},
            )
        elif input.operation == "update":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            repo.update_world_entry(input.project_id, input.identifier, data)
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
            repo.delete_world_entry(input.project_id, input.identifier)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
            )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False,
            error=f"world_entry only supports add/update/delete (got {input.operation})",
        )

    # ============ TimelineEvent（v003 拆为事件级）============
    async def _edit_timeline_event(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        data = input.data or {}

        if input.operation == "add":
            event_id = repo.add_timeline_event(input.project_id, data)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=event_id, success=True,
                affected={"event_id": event_id},
            )
        elif input.operation == "update":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            repo.update_timeline_event(input.project_id, input.identifier, data)
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
            repo.delete_timeline_event(input.project_id, input.identifier)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
            )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False,
            error=f"timeline_event only supports add/update/delete (got {input.operation})",
        )

    # ============ GeographyLocation（v003 拆为地点级）============
    async def _edit_geography_location(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        data = input.data or {}

        if input.operation == "add":
            location_id = repo.add_geography_location(input.project_id, data)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=location_id, success=True,
                affected={"location_id": location_id},
            )
        elif input.operation == "update":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            repo.update_geography_location(input.project_id, input.identifier, data)
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
            repo.delete_geography_location(input.project_id, input.identifier)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
            )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False,
            error=f"geography_location only supports add/update/delete (got {input.operation})",
        )

    # ============ Volume（v003 新增）============
    async def _edit_volume(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        data = input.data or {}

        if input.operation == "add":
            volume_id = repo.add_volume(input.project_id, data)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=volume_id, success=True,
                affected={"volume_id": volume_id},
            )
        elif input.operation == "update":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            repo.update_volume(input.project_id, input.identifier, data)
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
            repo.delete_volume(input.project_id, input.identifier)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
            )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False,
            error=f"volume only supports add/update/delete (got {input.operation})",
        )

    # ============ MainPlotNode（v003 新增 1:n 节点级）============
    async def _edit_main_plot_node(self, input: EditArtifactInput) -> EditArtifactResult:
        repo = ProjectRepository()
        data = input.data or {}

        if input.operation == "add":
            node_id = repo.add_main_plot_node(input.project_id, data)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=node_id, success=True,
                affected={"node_id": node_id},
            )
        elif input.operation == "update":
            if not input.identifier:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="identifier required",
                )
            repo.update_main_plot_node(input.project_id, input.identifier, data)
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
            repo.delete_main_plot_node(input.project_id, input.identifier)
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
            )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False,
            error=f"main_plot_node only supports add/update/delete (got {input.operation})",
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
        """Beat 编辑（main_plot.beats 数组）"""
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


from backend.services.project_manager import ProjectManager

register_tool(EditArtifactTool())
