"""EditArtifactTool — v0.4.1 结构化编辑 7 件基座

管家 Agent LLM 解析 user message → 调本工具（add/update/delete）

对应 core.md §B.1
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from realtime_novel.agent.tools.base import BaseTool, ToolError, register_tool
from realtime_novel.agent.tools.schemas import (
    EditArtifactInput, EditArtifactResult,
)
from realtime_novel.persistence import get_store, ProjectRepository


def _now() -> datetime:
    return datetime.now()


class EditArtifactTool(BaseTool):
    """结构化增量编辑 7 件基座

    9 个 target × 3 个 operation = 27 种组合，下面分块实现
    """
    name = "edit_artifact"
    description = "结构化编辑 7 件基座（add/update/delete）"

    input_schema = EditArtifactInput
    output_schema = EditArtifactResult

    def __init__(self):
        self._pm = AsyncProjectManager()

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
        with get_store().connection() as conn:
            if input.operation == "add":
                char_id = (input.data or {}).get("id", f"char-{uuid.uuid4().hex[:8]}")
                data = input.data or {}
                conn.execute(
                    """INSERT INTO characters (
                        id, project_id, name, role, traits_json, speech_style,
                        background, arc, internal_state, metadata_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        char_id, input.project_id,
                        data.get("name", ""), data.get("role", "supporting"),
                        json.dumps(data.get("traits", []), ensure_ascii=False),
                        data.get("speech_style"),
                        data.get("background"),
                        data.get("arc"),
                        data.get("internal_state"),
                        json.dumps(data.get("metadata", {}), ensure_ascii=False),
                        _now(),
                    ),
                )
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
                # diff merge
                row = conn.execute(
                    "SELECT * FROM characters WHERE id = ? AND project_id = ?",
                    (input.identifier, input.project_id),
                ).fetchone()
                if not row:
                    return EditArtifactResult(
                        project_id=input.project_id, target=input.target,
                        operation=input.operation, identifier=input.identifier, success=False,
                        error=f"character not found: {input.identifier}",
                    )
                old = dict(row)
                data = input.data or {}
                new_name = data.get("name", old["name"])
                new_role = data.get("role", old["role"])
                new_traits = data.get("traits", json.loads(old.get("traits_json") or "[]"))
                new_speech = data.get("speech_style", old.get("speech_style"))
                new_bg = data.get("background", old.get("background"))
                new_arc = data.get("arc", old.get("arc"))
                new_internal = data.get("internal_state", old.get("internal_state"))
                conn.execute(
                    """UPDATE characters SET
                        name=?, role=?, traits_json=?, speech_style=?,
                        background=?, arc=?, internal_state=?, updated_at=?
                    WHERE id=? AND project_id=?""",
                    (
                        new_name, new_role,
                        json.dumps(new_traits, ensure_ascii=False),
                        new_speech, new_bg, new_arc, new_internal, _now(),
                        input.identifier, input.project_id,
                    ),
                )
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, identifier=input.identifier, success=True,
                    affected={"char_id": input.identifier, "name": new_name},
                )
            elif input.operation == "delete":
                if not input.identifier:
                    return EditArtifactResult(
                        project_id=input.project_id, target=input.target,
                        operation=input.operation, success=False,
                        error="identifier required for delete",
                    )
                conn.execute(
                    "DELETE FROM characters WHERE id = ? AND project_id = ?",
                    (input.identifier, input.project_id),
                )
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
        with get_store().connection() as conn:
            if input.operation == "add":
                rel_id = (input.data or {}).get("id", f"rel-{uuid.uuid4().hex[:8]}")
                data = input.data or {}
                # 校验 character ID 存在
                from_id = data.get("from_char")
                to_id = data.get("to_char")
                if not (from_id and to_id):
                    return EditArtifactResult(
                        project_id=input.project_id, target=input.target,
                        operation=input.operation, success=False,
                        error="data.from_char and data.to_char required",
                    )
                conn.execute(
                    """INSERT INTO character_relationships (
                        id, project_id, from_char_id, to_char_id, type,
                        description, evolution_json, metadata_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rel_id, input.project_id, from_id, to_id,
                        data.get("type"), data.get("description"),
                        json.dumps(data.get("evolution", []), ensure_ascii=False),
                        json.dumps(data.get("metadata", {}), ensure_ascii=False),
                        _now(),
                    ),
                )
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
                conn.execute(
                    "DELETE FROM character_relationships WHERE id = ? AND project_id = ?",
                    (input.identifier, input.project_id),
                )
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
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT core_rules_json FROM world_tree WHERE project_id = ?",
                (input.project_id,),
            ).fetchone()
            if not row:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False,
                    error="world_tree not found",
                )
            rules = json.loads(row["core_rules_json"] or "[]")

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

            conn.execute(
                "UPDATE world_tree SET core_rules_json = ?, updated_at = ? WHERE project_id = ?",
                (json.dumps(rules, ensure_ascii=False), _now(), input.project_id),
            )
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
                affected={"rule_count": len(rules)},
            )

    # ============ Timeline / Geography ============

    async def _edit_timeline(self, input: EditArtifactInput) -> EditArtifactResult:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM world_tree WHERE project_id = ?",
                (input.project_id,),
            ).fetchone()
            if not row:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="world_tree not found",
                )
            data = input.data or {}
            year_range = data.get("year_range")
            year_start = year_range.get("start") if isinstance(year_range, dict) else None
            year_end = year_range.get("end") if isinstance(year_range, dict) else None
            conn.execute(
                """UPDATE world_tree SET
                    timeline_era=?, year_range_start=?, year_range_end=?, anchor_event=?, updated_at=?
                WHERE project_id=?""",
                (
                    data.get("era", row["timeline_era"]),
                    year_start if year_start is not None else row["year_range_start"],
                    year_end if year_end is not None else row["year_range_end"],
                    data.get("anchor_event", row["anchor_event"]),
                    _now(), input.project_id,
                ),
            )
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation="update", success=True,
                affected={"era": data.get("era")},
            )

    async def _edit_geography(self, input: EditArtifactInput) -> EditArtifactResult:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM world_tree WHERE project_id = ?",
                (input.project_id,),
            ).fetchone()
            if not row:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="world_tree not found",
                )
            data = input.data or {}
            conn.execute(
                """UPDATE world_tree SET
                    geography_primary=?, geography_secondary_json=?, geography_spatial_rules_json=?, updated_at=?
                WHERE project_id=?""",
                (
                    data.get("primary", row["geography_primary"]),
                    json.dumps(data.get("secondary", json.loads(row["geography_secondary_json"] or "[]")), ensure_ascii=False),
                    json.dumps(data.get("spatial_rules", json.loads(row["geography_spatial_rules_json"] or "[]") if row["geography_spatial_rules_json"] else []), ensure_ascii=False),
                    _now(), input.project_id,
                ),
            )
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation="update", success=True,
                affected={"primary": data.get("primary")},
            )

    # ============ Seed ============

    async def _edit_seed(self, input: EditArtifactInput) -> EditArtifactResult:
        with get_store().connection() as conn:
            if input.operation == "add":
                data = input.data or {}
                cursor = conn.execute(
                    """INSERT INTO seeds (
                        project_id, content, importance_primary, size, planned_interval,
                        orientation, planted_at_chapter, planted_in_node, planted_context,
                        last_seen_chapter, weight, status, linked_char_ids_json,
                        linked_subplot_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        input.project_id,
                        data.get("content", ""),
                        data.get("importance_primary", "小巧思"),
                        data.get("size", "点状"),
                        data.get("planned_interval"),
                        data.get("orientation", "氛围营造"),
                        data.get("planted_at_chapter", 0),
                        data.get("planted_in_node"),
                        data.get("planted_context"),
                        data.get("last_seen_chapter", 0),
                        data.get("weight", 0.5),
                        data.get("status", "planted"),
                        json.dumps(data.get("linked_char_ids", []), ensure_ascii=False),
                        data.get("linked_subplot_id"),
                        _now(),
                    ),
                )
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, identifier=str(cursor.lastrowid), success=True,
                    affected={"seed_id": cursor.lastrowid},
                )
            elif input.operation == "update":
                if not input.identifier:
                    return EditArtifactResult(
                        project_id=input.project_id, target=input.target,
                        operation=input.operation, success=False, error="identifier required",
                    )
                row = conn.execute(
                    "SELECT * FROM seeds WHERE id = ? AND project_id = ?",
                    (int(input.identifier), input.project_id),
                ).fetchone()
                if not row:
                    return EditArtifactResult(
                        project_id=input.project_id, target=input.target,
                        operation=input.operation, identifier=input.identifier, success=False,
                        error=f"seed not found: {input.identifier}",
                    )
                old = dict(row)
                data = input.data or {}
                conn.execute(
                    """UPDATE seeds SET
                        content=?, importance_primary=?, size=?, planned_interval=?,
                        orientation=?, weight=?, status=?, updated_at=?
                    WHERE id=? AND project_id=?""",
                    (
                        data.get("content", old["content"]),
                        data.get("importance_primary", old["importance_primary"]),
                        data.get("size", old["size"]),
                        data.get("planned_interval", old["planned_interval"]),
                        data.get("orientation", old["orientation"]),
                        data.get("weight", old["weight"]),
                        data.get("status", old["status"]),
                        _now(), int(input.identifier), input.project_id,
                    ),
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
                conn.execute(
                    "DELETE FROM seeds WHERE id = ? AND project_id = ?",
                    (int(input.identifier), input.project_id),
                )
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, identifier=input.identifier, success=True,
                )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False, error="unsupported",
        )

    # ============ Subplot / Beat（简化版）============

    async def _edit_subplot(self, input: EditArtifactInput) -> EditArtifactResult:
        with get_store().connection() as conn:
            if input.operation == "add":
                sp_id = (input.data or {}).get("id", f"subplot-{uuid.uuid4().hex[:8]}")
                data = input.data or {}
                conn.execute(
                    """INSERT INTO sub_plot (
                        id, project_id, title, description, parent_beat_id, status, priority,
                        linked_seeds_json, linked_chars_json, beats_json, metadata_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sp_id, input.project_id,
                        data.get("title", ""), data.get("description"),
                        data.get("parent_beat_id"),
                        data.get("status", "pending"),
                        data.get("priority", "side"),
                        json.dumps(data.get("linked_seeds", []), ensure_ascii=False),
                        json.dumps(data.get("linked_chars", []), ensure_ascii=False),
                        json.dumps(data.get("beats", []), ensure_ascii=False),
                        json.dumps(data.get("metadata", {}), ensure_ascii=False),
                        _now(),
                    ),
                )
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
                conn.execute(
                    "DELETE FROM sub_plot WHERE id = ? AND project_id = ?",
                    (input.identifier, input.project_id),
                )
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, identifier=input.identifier, success=True,
                )
        return EditArtifactResult(
            project_id=input.project_id, target=input.target,
            operation=input.operation, success=False, error="unsupported",
        )

    async def _edit_beat(self, input: EditArtifactInput) -> EditArtifactResult:
        """Beat 编辑（main_plot.beats 数组，JSON 形式）"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT beats_json FROM main_plot WHERE project_id = ?",
                (input.project_id,),
            ).fetchone()
            if not row:
                return EditArtifactResult(
                    project_id=input.project_id, target=input.target,
                    operation=input.operation, success=False, error="main_plot not found",
                )
            beats = json.loads(row["beats_json"] or "[]")

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
                        error=f"beat not found",
                    )
            elif input.operation == "delete":
                if not input.identifier:
                    return EditArtifactResult(
                        project_id=input.project_id, target=input.target,
                        operation=input.operation, success=False, error="identifier required",
                    )
                beats = [b for b in beats if b.get("id") != input.identifier]

            conn.execute(
                "UPDATE main_plot SET beats_json = ?, updated_at = ? WHERE project_id = ?",
                (json.dumps(beats, ensure_ascii=False), _now(), input.project_id),
            )
            return EditArtifactResult(
                project_id=input.project_id, target=input.target,
                operation=input.operation, identifier=input.identifier, success=True,
                affected={"beat_count": len(beats)},
            )


# 补上 AsyncProjectManager import
from realtime_novel.services.async_wrappers import AsyncProjectManager

# 注册
register_tool(EditArtifactTool())
