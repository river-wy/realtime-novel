"""ProjectRepository：projects + world_tree 基座 + 9 张关联表

v003 重构（spec: .spec/db-refactor/spec.md）
- 删：palette（迁前端主题）、current_pov（迁 project_state）、6 件基座（重构成 9 张表）
- 删：update_timeline / update_geography（旧列级更新）
- 新增：project_state / volumes / main_plot_node / sub_plot / world_entries / timeline_events / geography_locations 方法
- _upsert_world_tree 重写：仅写 5 字段（story_core / genre_tags_json / core_rules_json）
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from backend.persistence.models import (
    Project, ProjectState, WorldTreeRow,
    VolumeRow, MainPlotNodeRow, SubPlotRow,
    CharacterRow, CharacterRelationshipRow,
    SeedRow, TimelineEventRow, GeographyLocationRow, WorldEntryRow,
)
from backend.persistence.sqlite_store import get_store
from backend.utils.logger import logger


def _now() -> datetime:
    return datetime.now()


def _to_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _from_json(value: Optional[str]) -> Any:
    if value is None:
        return None
    return json.loads(value)


# ============ Project CRUD ============

@logger
class ProjectRepository:
    """projects + 9 张关联表（世界树基座）"""

    # ---------- projects ----------

    def create(self, project_id: str, name: str,
               exploration_level: str = "standard",
               style_pack_id: Optional[str] = None) -> Project:
        """v003：删 palette 入参"""
        now = _now()
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, exploration_level, style_pack_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, name, exploration_level, style_pack_id, now, now),
            )
        self.log.info(
            "DB project CREATE: id=%s, name=%r, exploration_level=%s, style_pack_id=%s",
            project_id, name, exploration_level, style_pack_id,
        )
        return Project(
            id=project_id, name=name,
            exploration_level=exploration_level,
            style_pack_id=style_pack_id,
            created_at=now, updated_at=now,
        )

    def get(self, project_id: str) -> Optional[Project]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        return Project(**dict(row))

    def list_all(self, limit: int = 50) -> List[Project]:
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE deleted_at IS NULL "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [Project(**dict(r)) for r in rows]

    def update_name(self, project_id: str, new_name: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                (new_name, _now(), project_id),
            )

    def update_exploration_level(self, project_id: str, new_level: str) -> None:
        if new_level not in ("conservative", "standard", "wild"):
            raise ValueError(f"exploration_level 必须是 conservative/standard/wild, 收到: {new_level!r}")
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET exploration_level = ?, updated_at = ? WHERE id = ?",
                (new_level, _now(), project_id),
            )

    def update_style_pack_id(self, project_id: str, style_pack_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET style_pack_id = ?, updated_at = ? WHERE id = ?",
                (style_pack_id, _now(), project_id),
            )

    def get_style_pack_id(self, project_id: str) -> Optional[str]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT style_pack_id FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        if row:
            return row[0] or None
        return None

    def update_cover_image_url(self, project_id: str, cover_image_url: Optional[str]) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET cover_image_url = ?, updated_at = ? WHERE id = ?",
                (cover_image_url, _now(), project_id),
            )

    def soft_delete(self, project_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET deleted_at = ? WHERE id = ?",
                (_now(), project_id),
            )

    def hard_delete(self, project_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def restore_delete(self, project_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET deleted_at = NULL WHERE id = ?",
                (project_id,),
            )

    # ---------- project_state (1:1) ----------

    def get_project_state(self, project_id: str) -> Optional[ProjectState]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM project_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        return ProjectState(**dict(row))

    def upsert_project_state(
        self,
        project_id: str,
        current_pov: Optional[str] = None,
        current_chapter: Optional[int] = None,
        current_volume_id: Optional[str] = None,
        current_timeline_event_id: Optional[str] = None,
        current_geography_location_ids: Optional[List[str]] = None,
        last_generated_at: Optional[datetime] = None,
    ) -> None:
        """upsert project_state（v003 新增）"""
        now = _now()
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM project_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if row:
                # 增量 UPDATE：仅更新非 None 字段
                fields = []
                values = []
                if current_pov is not None:
                    fields.append("current_pov = ?")
                    values.append(current_pov)
                if current_chapter is not None:
                    fields.append("current_chapter = ?")
                    values.append(current_chapter)
                if current_volume_id is not None:
                    fields.append("current_volume_id = ?")
                    values.append(current_volume_id)
                if current_timeline_event_id is not None:
                    fields.append("current_timeline_event_id = ?")
                    values.append(current_timeline_event_id)
                if current_geography_location_ids is not None:
                    fields.append("current_geography_location_ids_json = ?")
                    values.append(_to_json(current_geography_location_ids))
                if last_generated_at is not None:
                    fields.append("last_generated_at = ?")
                    values.append(last_generated_at)
                fields.append("updated_at = ?")
                values.append(now)
                values.append(project_id)
                conn.execute(
                    f"UPDATE project_state SET {', '.join(fields)} WHERE project_id = ?",
                    values,
                )
            else:
                conn.execute(
                    """
                    INSERT INTO project_state (
                        project_id, current_pov, current_chapter, current_volume_id,
                        current_timeline_event_id, current_geography_location_ids_json,
                        last_generated_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        current_pov,
                        current_chapter or 0,
                        current_volume_id,
                        current_timeline_event_id,
                        _to_json(current_geography_location_ids or []),
                        last_generated_at,
                        now,
                    ),
                )

    # ---------- world_tree (5 字段最终态) ----------

    def _upsert_world_tree(self, project_id: str, data: Dict[str, Any]) -> None:
        """v003 重写：仅写 5 字段

        输入 data 格式：
        - data["story_core"]: str（顶层）
        - data["genre_tags"]: list[str]（顶层，替代 genre_resonance）
        - data["base"]["core_rules"]: list[dict]（约束规则）
        """
        now = _now()
        story_core = data.get("story_core")
        genre_tags = data.get("genre_tags") or data.get("genres", [])
        base = data.get("base", {}) or {}
        core_rules = base.get("core_rules", [])

        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO world_tree (
                    project_id, story_core, genre_tags_json, core_rules_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    story_core=excluded.story_core,
                    genre_tags_json=excluded.genre_tags_json,
                    core_rules_json=excluded.core_rules_json,
                    updated_at=excluded.updated_at
                """,
                (
                    project_id,
                    story_core,
                    _to_json(genre_tags),
                    _to_json(core_rules),
                    now,
                ),
            )

    def get_world_tree(self, project_id: str) -> Optional[WorldTreeRow]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM world_tree WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        return WorldTreeRow(**dict(row))

    def get_core_rules(self, project_id: str) -> List[Dict[str, Any]]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT core_rules_json FROM world_tree WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if not row or not row["core_rules_json"]:
            return []
        return _from_json(row["core_rules_json"]) or []

    def save_core_rules(self, project_id: str, rules: List[Dict[str, Any]]) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE world_tree SET core_rules_json = ?, updated_at = ? WHERE project_id = ?",
                (_to_json(rules), _now(), project_id),
            )

    # ---------- volumes (1:n) ----------

    def list_volumes(self, project_id: str) -> List[VolumeRow]:
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM volumes WHERE project_id = ? ORDER BY volume_num",
                (project_id,),
            ).fetchall()
        return [VolumeRow(**dict(r)) for r in rows]

    def get_volume(self, project_id: str, volume_id: str) -> Optional[VolumeRow]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM volumes WHERE project_id = ? AND id = ?",
                (project_id, volume_id),
            ).fetchone()
        if not row:
            return None
        return VolumeRow(**dict(row))

    def add_volume(self, project_id: str, data: Dict[str, Any]) -> str:
        volume_id = data.get("id", f"vol-{uuid.uuid4().hex[:8]}")
        now = _now()
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO volumes (id, project_id, volume_num, title, description, planned_chapter_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    volume_id, project_id,
                    data.get("volume_num", 0),
                    data.get("title", ""),
                    data.get("description"),
                    data.get("planned_chapter_count"),
                    now,
                ),
            )
        self.log.info("DB volume ADD: project=%s, vol_id=%s", project_id, volume_id)
        return volume_id

    def update_volume(self, project_id: str, volume_id: str, data: Dict[str, Any]) -> None:
        fields = []
        values = []
        for key in ("volume_num", "title", "description", "planned_chapter_count"):
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(_now())
        values.extend([project_id, volume_id])
        with get_store().connection() as conn:
            conn.execute(
                f"UPDATE volumes SET {', '.join(fields)} WHERE project_id = ? AND id = ?",
                values,
            )

    def delete_volume(self, project_id: str, volume_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM volumes WHERE project_id = ? AND id = ?",
                (project_id, volume_id),
            )

    # ---------- main_plot (1:n 节点) ----------

    def list_main_plot_nodes(self, project_id: str) -> List[MainPlotNodeRow]:
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM main_plot WHERE project_id = ? ORDER BY plot_num",
                (project_id,),
            ).fetchall()
        return [MainPlotNodeRow(**dict(r)) for r in rows]

    def get_main_plot_node(self, project_id: str, node_id: str) -> Optional[MainPlotNodeRow]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM main_plot WHERE project_id = ? AND id = ?",
                (project_id, node_id),
            ).fetchone()
        if not row:
            return None
        return MainPlotNodeRow(**dict(row))

    def add_main_plot_node(self, project_id: str, data: Dict[str, Any]) -> str:
        node_id = data.get("id", f"mp-{uuid.uuid4().hex[:8]}")
        now = _now()
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO main_plot (
                    id, project_id, volume_id, plot_num, title, description,
                    estimated_chapter, status, related_char_ids_json,
                    related_timeline_event_id, related_geography_location_ids_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id, project_id,
                    data.get("volume_id"),
                    data.get("plot_num", 0),
                    data.get("title"),
                    data.get("description", ""),
                    data.get("estimated_chapter"),
                    data.get("status", "pending"),
                    _to_json(data.get("related_char_ids", [])),
                    data.get("related_timeline_event_id"),
                    _to_json(data.get("related_geography_location_ids", [])),
                    now,
                ),
            )
        return node_id

    def update_main_plot_node(self, project_id: str, node_id: str, data: Dict[str, Any]) -> None:
        fields = []
        values = []
        for key in ("volume_id", "plot_num", "title", "description", "estimated_chapter", "status",
                    "related_timeline_event_id"):
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if "related_char_ids" in data:
            fields.append("related_char_ids_json = ?")
            values.append(_to_json(data["related_char_ids"]))
        if "related_geography_location_ids" in data:
            fields.append("related_geography_location_ids_json = ?")
            values.append(_to_json(data["related_geography_location_ids"]))
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(_now())
        values.extend([project_id, node_id])
        with get_store().connection() as conn:
            conn.execute(
                f"UPDATE main_plot SET {', '.join(fields)} WHERE project_id = ? AND id = ?",
                values,
            )

    def delete_main_plot_node(self, project_id: str, node_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM main_plot WHERE project_id = ? AND id = ?",
                (project_id, node_id),
            )

    # ---------- sub_plot (1:n) ----------

    def list_subplots(self, project_id: str) -> List[SubPlotRow]:
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM sub_plot WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return [SubPlotRow(**dict(r)) for r in rows]

    def get_subplot(self, project_id: str, subplot_id: str) -> Optional[SubPlotRow]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM sub_plot WHERE project_id = ? AND id = ?",
                (project_id, subplot_id),
            ).fetchone()
        if not row:
            return None
        return SubPlotRow(**dict(row))

    def add_subplot(self, project_id: str, data: Dict[str, Any]) -> str:
        subplot_id = data.get("id", f"sub-{uuid.uuid4().hex[:8]}")
        now = _now()
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO sub_plot (
                    id, project_id, volume_id, title, description, chapter_start, chapter_end,
                    status, priority, related_char_ids_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    subplot_id, project_id,
                    data.get("volume_id"),
                    data.get("title", ""),
                    data.get("description"),
                    data.get("chapter_start"),
                    data.get("chapter_end"),
                    data.get("status", "pending"),
                    data.get("priority", "side"),
                    _to_json(data.get("related_char_ids", [])),
                    now,
                ),
            )
        return subplot_id

    def update_subplot(self, project_id: str, subplot_id: str, data: Dict[str, Any]) -> None:
        fields = []
        values = []
        for key in ("volume_id", "title", "description", "chapter_start", "chapter_end", "status", "priority"):
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if "related_char_ids" in data:
            fields.append("related_char_ids_json = ?")
            values.append(_to_json(data["related_char_ids"]))
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(_now())
        values.extend([project_id, subplot_id])
        with get_store().connection() as conn:
            conn.execute(
                f"UPDATE sub_plot SET {', '.join(fields)} WHERE project_id = ? AND id = ?",
                values,
            )

    def delete_subplot(self, project_id: str, subplot_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM sub_plot WHERE project_id = ? AND id = ?",
                (project_id, subplot_id),
            )

    # ---------- timeline_events (1:n) ----------

    def list_timeline_events(self, project_id: str) -> List[TimelineEventRow]:
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM timeline_events WHERE project_id = ? "
                "ORDER BY era_order, event_order",
                (project_id,),
            ).fetchall()
        return [TimelineEventRow(**dict(r)) for r in rows]

    def add_timeline_event(self, project_id: str, data: Dict[str, Any]) -> str:
        event_id = data.get("id", f"evt-{uuid.uuid4().hex[:8]}")
        now = _now()
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO timeline_events (
                    id, project_id, era_name, era_order, event_name, description,
                    event_order, start_year, end_year,
                    related_main_plot_node_id, related_char_ids_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, project_id,
                    data.get("era_name", ""),
                    data.get("era_order"),
                    data.get("event_name", ""),
                    data.get("description"),
                    data.get("event_order"),
                    data.get("start_year"),
                    data.get("end_year"),
                    data.get("related_main_plot_node_id"),
                    _to_json(data.get("related_char_ids", [])),
                    now,
                ),
            )
        return event_id

    def update_timeline_event(self, project_id: str, event_id: str, data: Dict[str, Any]) -> None:
        fields = []
        values = []
        for key in ("era_name", "era_order", "event_name", "description", "event_order",
                    "start_year", "end_year", "related_main_plot_node_id"):
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if "related_char_ids" in data:
            fields.append("related_char_ids_json = ?")
            values.append(_to_json(data["related_char_ids"]))
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(_now())
        values.extend([project_id, event_id])
        with get_store().connection() as conn:
            conn.execute(
                f"UPDATE timeline_events SET {', '.join(fields)} WHERE project_id = ? AND id = ?",
                values,
            )

    def delete_timeline_event(self, project_id: str, event_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM timeline_events WHERE project_id = ? AND id = ?",
                (project_id, event_id),
            )

    # ---------- geography_locations (1:n) ----------

    def list_geography_locations(self, project_id: str) -> List[GeographyLocationRow]:
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM geography_locations WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return [GeographyLocationRow(**dict(r)) for r in rows]

    def add_geography_location(self, project_id: str, data: Dict[str, Any]) -> str:
        location_id = data.get("id", f"loc-{uuid.uuid4().hex[:8]}")
        now = _now()
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO geography_locations (
                    id, project_id, name, category, description, significance,
                    parent_location_id, related_char_ids_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    location_id, project_id,
                    data.get("name", ""),
                    data.get("category", "region"),
                    data.get("description"),
                    data.get("significance"),
                    data.get("parent_location_id"),
                    _to_json(data.get("related_char_ids", [])),
                    now,
                ),
            )
        return location_id

    def update_geography_location(self, project_id: str, location_id: str, data: Dict[str, Any]) -> None:
        fields = []
        values = []
        for key in ("name", "category", "description", "significance", "parent_location_id"):
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if "related_char_ids" in data:
            fields.append("related_char_ids_json = ?")
            values.append(_to_json(data["related_char_ids"]))
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(_now())
        values.extend([project_id, location_id])
        with get_store().connection() as conn:
            conn.execute(
                f"UPDATE geography_locations SET {', '.join(fields)} WHERE project_id = ? AND id = ?",
                values,
            )

    def delete_geography_location(self, project_id: str, location_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM geography_locations WHERE project_id = ? AND id = ?",
                (project_id, location_id),
            )

    # ---------- world_entries (1:n) ----------

    def list_world_entries(self, project_id: str, category: Optional[str] = None) -> List[WorldEntryRow]:
        with get_store().connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM world_entries WHERE project_id = ? AND category = ?",
                    (project_id, category),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM world_entries WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
        return [WorldEntryRow(**dict(r)) for r in rows]

    def add_world_entry(self, project_id: str, data: Dict[str, Any]) -> str:
        entry_id = data.get("id", f"we-{uuid.uuid4().hex[:8]}")
        now = _now()
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO world_entries (
                    id, project_id, category, title, content,
                    related_char_ids_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id, project_id,
                    data.get("category", "other"),
                    data.get("title", ""),
                    data.get("content", ""),
                    _to_json(data.get("related_char_ids", [])),
                    now,
                ),
            )
        return entry_id

    def update_world_entry(self, project_id: str, entry_id: str, data: Dict[str, Any]) -> None:
        fields = []
        values = []
        for key in ("category", "title", "content"):
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if "related_char_ids" in data:
            fields.append("related_char_ids_json = ?")
            values.append(_to_json(data["related_char_ids"]))
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(_now())
        values.extend([project_id, entry_id])
        with get_store().connection() as conn:
            conn.execute(
                f"UPDATE world_entries SET {', '.join(fields)} WHERE project_id = ? AND id = ?",
                values,
            )

    def delete_world_entry(self, project_id: str, entry_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM world_entries WHERE project_id = ? AND id = ?",
                (project_id, entry_id),
            )

    # ---------- characters (1:n) ----------

    def list_characters(self, project_id: str) -> List[CharacterRow]:
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM characters WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return [CharacterRow(**dict(r)) for r in rows]

    def get_character(self, project_id: str, char_id: str) -> Optional[CharacterRow]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM characters WHERE id = ? AND project_id = ?",
                (char_id, project_id),
            ).fetchone()
        if not row:
            return None
        return CharacterRow(**dict(row))

    def add_character(self, project_id: str, data: Dict[str, Any]) -> str:
        char_id = data.get("id", f"char-{uuid.uuid4().hex[:8]}")
        now = _now()
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO characters (
                    id, project_id, name, role, traits_json, speech_style, background, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    char_id, project_id,
                    data.get("name", ""),
                    data.get("role", "supporting"),
                    _to_json(data.get("traits", [])),
                    data.get("speech_style"),
                    data.get("background"),
                    now,
                ),
            )
        return char_id

    def update_character(self, project_id: str, char_id: str, data: Dict[str, Any]) -> None:
        fields = []
        values = []
        for key in ("name", "role", "speech_style", "background"):
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if "traits" in data:
            fields.append("traits_json = ?")
            values.append(_to_json(data["traits"]))
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(_now())
        values.extend([project_id, char_id])
        with get_store().connection() as conn:
            conn.execute(
                f"UPDATE characters SET {', '.join(fields)} WHERE project_id = ? AND id = ?",
                values,
            )

    def delete_character(self, project_id: str, char_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM characters WHERE project_id = ? AND id = ?",
                (project_id, char_id),
            )

    # ---------- character_relationships (1:n) ----------

    def list_relationships(self, project_id: str) -> List[CharacterRelationshipRow]:
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM character_relationships WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return [CharacterRelationshipRow(**dict(r)) for r in rows]

    def add_relationship(self, project_id: str, data: Dict[str, Any]) -> str:
        rel_id = data.get("id", f"rel-{uuid.uuid4().hex[:8]}")
        # 规范化：保证 char_a_id < char_b_id
        a = data.get("char_a_id", "")
        b = data.get("char_b_id", "")
        if a >= b:
            a, b = b, a
        now = _now()
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO character_relationships (
                    id, project_id, char_a_id, char_b_id, rel_type, description, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rel_id, project_id, a, b,
                    data.get("rel_type", "friend"),
                    data.get("description"),
                    now,
                ),
            )
        return rel_id

    def delete_relationship(self, project_id: str, rel_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM character_relationships WHERE project_id = ? AND id = ?",
                (project_id, rel_id),
            )

    # ---------- seeds (1:n, 单表含运行时状态) ----------

    def list_seeds(self, project_id: str, status: Optional[str] = None) -> List[SeedRow]:
        with get_store().connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM seeds WHERE project_id = ? AND status = ?",
                    (project_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM seeds WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
        return [SeedRow(**dict(r)) for r in rows]

    def get_seed(self, project_id: str, seed_id: int) -> Optional[SeedRow]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM seeds WHERE project_id = ? AND id = ?",
                (project_id, seed_id),
            ).fetchone()
        if not row:
            return None
        return SeedRow(**dict(row))

    def add_seed(self, project_id: str, data: Dict[str, Any]) -> int:
        now = _now()
        with get_store().connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO seeds (
                    project_id, name, content, trigger, payoff,
                    category, scope, estimated_plant_chapter, estimated_payoff_chapter,
                    related_char_ids_json, related_main_plot_node_id, related_sub_plot_id,
                    status, weight, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    data.get("name", ""),
                    data.get("content", ""),
                    data.get("trigger"),
                    data.get("payoff"),
                    data.get("category", "plot"),
                    data.get("scope", "mid"),
                    data.get("estimated_plant_chapter"),
                    data.get("estimated_payoff_chapter"),
                    _to_json(data.get("related_char_ids", [])),
                    data.get("related_main_plot_node_id"),
                    data.get("related_sub_plot_id"),
                    data.get("status", "pending"),
                    data.get("weight", 0.5),
                    now,
                ),
            )
            return cursor.lastrowid

    def update_seed(self, project_id: str, seed_id: int, data: Dict[str, Any]) -> None:
        fields = []
        values = []
        for key in ("name", "content", "trigger", "payoff", "category", "scope",
                    "estimated_plant_chapter", "estimated_payoff_chapter",
                    "related_main_plot_node_id", "related_sub_plot_id",
                    "status", "weight",
                    "planted_at_chapter", "planted_context", "last_seen_chapter"):
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if "related_char_ids" in data:
            fields.append("related_char_ids_json = ?")
            values.append(_to_json(data["related_char_ids"]))
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(_now())
        values.extend([project_id, seed_id])
        with get_store().connection() as conn:
            conn.execute(
                f"UPDATE seeds SET {', '.join(fields)} WHERE project_id = ? AND id = ?",
                values,
            )

    def delete_seed(self, project_id: str, seed_id: int) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM seeds WHERE project_id = ? AND id = ?",
                (project_id, seed_id),
            )

    # ---------- 综合查询（context builder 用） ----------

    def load_all_artifacts(self, project_id: str) -> Dict[str, Any]:
        """一次性读所有世界树基座表（context builder 用）

        v003：返回新 schema 的字段集
        """
        return {
            "world_tree": self.get_world_tree(project_id),
            "project_state": self.get_project_state(project_id),
            "volumes": self.list_volumes(project_id),
            "main_plot": self.list_main_plot_nodes(project_id),
            "sub_plot": self.list_subplots(project_id),
            "characters": self.list_characters(project_id),
            "character_relationships": self.list_relationships(project_id),
            "seeds": self.list_seeds(project_id),
            "world_entries": self.list_world_entries(project_id),
            "timeline_events": self.list_timeline_events(project_id),
            "geography_locations": self.list_geography_locations(project_id),
        }
