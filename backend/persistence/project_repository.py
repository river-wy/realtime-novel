"""ProjectRepository：projects 表 + 6 件基座 CRUD

所有 JSON 字段在 Repository 边界做序列化/反序列化。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from backend.persistence.models import (
    Project, )
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
    """projects 表 CRUD + 6 件基座"""

    # ----- Project 元数据 -----

    def create(self, project_id: str, name: str, palette: str = "",
               exploration_level: str = "standard",
               style_pack_id: Optional[str] = None) -> Project:
        """创建项目"""
        now = _now()
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, palette, exploration_level, style_pack_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, name, palette, exploration_level, style_pack_id, now, now),
            )
        self.log.info("DB project CREATE: id=%s, name=%r, exploration_level=%s, style_pack_id=%s",
                      project_id, name, exploration_level, style_pack_id)
        return Project(
            id=project_id, name=name, palette=palette,
            exploration_level=exploration_level,
            style_pack_id=style_pack_id,
            current_pov=None, created_at=now, updated_at=now,
        )

    def update_style_pack_id(self, project_id: str, style_pack_id: str) -> None:
        """更新写作笔风 id"""
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET style_pack_id = ?, updated_at = ? WHERE id = ?",
                (style_pack_id, _now(), project_id),
            )
        self.log.info("DB project UPDATE style_pack_id: id=%s, style_pack_id=%s", project_id, style_pack_id)

    def get_style_pack_id(self, project_id: str) -> Optional[str]:
        """读取写作笔风 id，不存在返回 None"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT style_pack_id FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        if row:
            return row[0] or None
        return None

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
        self.log.info("DB project UPDATE name: id=%s, name=%r", project_id, new_name)

    def update_palette(self, project_id: str, new_palette: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET palette = ?, updated_at = ? WHERE id = ?",
                (new_palette, _now(), project_id),
            )

    def update_exploration_level(self, project_id: str, new_level: str) -> None:
        """切换探索度 (conservative/standard/wild)"""
        if new_level not in ("conservative", "standard", "wild"):
            raise ValueError(f"exploration_level 必须是 conservative/standard/wild, 收到: {new_level!r}")
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET exploration_level = ?, updated_at = ? WHERE id = ?",
                (new_level, _now(), project_id),
            )
        self.log.info("DB project UPDATE exploration_level: id=%s, level=%s", project_id, new_level)

    def update_current_pov(self, project_id: str, new_pov: Optional[str]) -> None:
        """更新 POV 角色 char_id"""
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET current_pov = ?, updated_at = ? WHERE id = ?",
                (new_pov, _now(), project_id),
            )

    def update_cover_image_url(self, project_id: str, cover_image_url: Optional[str]) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET cover_image_url = ?, updated_at = ? WHERE id = ?",
                (cover_image_url, _now(), project_id),
            )
        self.log.info("DB project UPDATE cover_image_url: id=%s, url=%s", project_id, cover_image_url)

    def soft_delete(self, project_id: str) -> None:
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET deleted_at = ? WHERE id = ?",
                (_now(), project_id),
            )
        self.log.info("DB project SOFT DELETE: id=%s", project_id)

    def hard_delete(self, project_id: str) -> None:
        """物理删除（cascade 删 6 件基座）"""
        with get_store().connection() as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.log.info("DB project HARD DELETE: id=%s", project_id)

    def restore_delete(self, project_id: str) -> None:
        """取消软删标记"""
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET deleted_at = NULL WHERE id = ?",
                (project_id,),
            )
        self.log.info("DB project RESTORE: id=%s", project_id)

    # ----- 6 件基座 upsert -----

    def _upsert_world_tree(self, project_id: str, data: Dict[str, Any]) -> None:
        base = data.get("base", {}) or {}
        timeline = base.get("timeline", {}) or {}
        geography = base.get("geography", {}) or {}
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO world_tree (
                    project_id, timeline_era, anchor_event,
                    geography_primary, geography_secondary_json, geography_spatial_rules_json,
                    core_rules_json, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    timeline_era=excluded.timeline_era,
                    anchor_event=excluded.anchor_event,
                    geography_primary=excluded.geography_primary,
                    geography_secondary_json=excluded.geography_secondary_json,
                    geography_spatial_rules_json=excluded.geography_spatial_rules_json,
                    core_rules_json=excluded.core_rules_json,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    project_id,
                    timeline.get("era"),
                    timeline.get("anchor_event"),
                    geography.get("primary"),
                    _to_json(geography.get("secondary", [])),
                    _to_json(geography.get("spatial_rules")),
                    _to_json(base.get("core_rules", [])),
                    _to_json(data.get("metadata", {})),
                    _now(),
                ),
            )

    def _upsert_genre_resonance(self, project_id: str, data: Dict[str, Any]) -> None:
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO genre_resonance (
                    project_id, accept_json, reject_json, anchors_json, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    accept_json=excluded.accept_json,
                    reject_json=excluded.reject_json,
                    anchors_json=excluded.anchors_json,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    project_id,
                    _to_json(data.get("accept", [])),
                    _to_json(data.get("reject", [])),
                    _to_json(data.get("anchors", [])),
                    _to_json(data.get("metadata", {})),
                    _now(),
                ),
            )

    def _upsert_main_plot(self, project_id: str, data: Dict[str, Any]) -> None:
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO main_plot (
                    project_id, current_beat, arc_phrase, beats_json, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    current_beat=excluded.current_beat,
                    arc_phrase=excluded.arc_phrase,
                    beats_json=excluded.beats_json,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    project_id,
                    data.get("current_beat", 0),
                    data.get("arc_phrase"),
                    _to_json(data.get("beats", [])),
                    _to_json(data.get("metadata", {})),
                    _now(),
                ),
            )

    def _replace_subplots(self, project_id: str, sub_plots: List[Dict[str, Any]]) -> None:
        """支线一对多：先删后插（显式事务）"""
        with get_store().transaction() as conn:
            conn.execute("DELETE FROM sub_plot WHERE project_id = ?", (project_id,))
            for sp in sub_plots or []:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO sub_plot (
                        id, project_id, title, description, parent_beat_id, status, priority,
                        linked_seeds_json, linked_chars_json, metadata_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sp.get("id", f"subplot-{uuid.uuid4().hex[:8]}"),
                        project_id,
                        sp.get("title", ""),
                        sp.get("description"),
                        sp.get("parent_beat_id"),
                        sp.get("status", "pending"),
                        sp.get("priority", "side"),
                        _to_json(sp.get("linked_seeds", [])),
                        _to_json(sp.get("linked_chars", [])),
                        _to_json(sp.get("metadata", {})),
                        _now(),
                    ),
                )

    def _replace_characters(self, project_id: str, char_card: Dict[str, Any]) -> None:
        """角色 + 关系一对多：先删角色（cascade 删关系），显式事务"""
        characters = char_card.get("characters", []) or []
        relationships = char_card.get("relationships", []) or []
        with get_store().transaction() as conn:
            conn.execute("DELETE FROM characters WHERE project_id = ?", (project_id,))
            for c in characters:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO characters (
                        id, project_id, name, role, traits_json, speech_style,
                        background, arc, internal_state, metadata_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        c.get("id", f"char-{uuid.uuid4().hex[:8]}"),
                        project_id,
                        c.get("name", ""),
                        c.get("role", "supporting"),
                        _to_json(c.get("traits", [])),
                        c.get("speech_style"),
                        c.get("background"),
                        c.get("arc"),
                        c.get("internal_state"),
                        _to_json(c.get("metadata", {})),
                        _now(),
                    ),
                )
            for r in relationships:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO character_relationships (
                        id, project_id, from_char_id, to_char_id, type,
                        description, evolution_json, metadata_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r.get("id", f"rel-{uuid.uuid4().hex[:8]}"),
                        project_id,
                        r.get("from_char"),
                        r.get("to_char"),
                        r.get("type"),
                        r.get("description"),
                        _to_json(r.get("evolution", [])),
                        _to_json(r.get("metadata", {})),
                        _now(),
                    ),
                )

    def _replace_seeds(self, project_id: str, seeds: List[Dict[str, Any]]) -> None:
        """种子一对多：先删后插（显式事务）"""
        with get_store().transaction() as conn:
            conn.execute("DELETE FROM seeds WHERE project_id = ?", (project_id,))
            for s in seeds or []:
                importance = s.get("importance", {}) or {}
                conn.execute(
                    """
                    INSERT INTO seeds (
                        project_id, content, name, trigger, payoff,
                        estimated_chapter, payoff_chapter,
                        importance_primary, size, planned_interval,
                        orientation, planted_at_chapter, planted_in_node, planted_context,
                        last_seen_chapter, weight, status, linked_char_ids_json,
                        linked_subplot_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        s.get("content", ""),
                        s.get("name"),
                        s.get("trigger"),
                        s.get("payoff"),
                        s.get("estimated_chapter"),
                        s.get("payoff_chapter"),
                        importance.get("primary", "小巧思"),
                        s.get("size", "点状"),
                        s.get("planned_interval"),
                        s.get("orientation", "氛围营造"),
                        s.get("planted_at_chapter", 0),
                        s.get("planted_in_node"),
                        s.get("planted_context"),
                        s.get("last_seen_chapter", 0),
                        s.get("weight", 0.5),
                        s.get("status", "planted"),
                        _to_json(s.get("linked_char_ids", [])),
                        s.get("linked_subplot_id"),
                        _now(),
                    ),
                )

    def save_7_artifacts(
        self,
        project_id: str,
        world_tree: Dict[str, Any],
        genre_resonance: Dict[str, Any],
        main_plot: Dict[str, Any],
        sub_plot: Dict[str, Any],
        character_card: Dict[str, Any],
        seed_table: Dict[str, Any],
    ) -> None:
        """6 件基座一次性落库"""
        self._upsert_world_tree(project_id, world_tree)
        self._upsert_genre_resonance(project_id, genre_resonance)
        self._upsert_main_plot(project_id, main_plot)
        threads = sub_plot.get("threads", []) if isinstance(sub_plot, dict) else []
        self._replace_subplots(project_id, threads)
        self._replace_characters(project_id, character_card)
        seeds = seed_table.get("seeds", []) if isinstance(seed_table, dict) else []
        self._replace_seeds(project_id, seeds)
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (_now(), project_id),
            )

    # ----- 6 件基座读取 -----

    def load_all_artifacts(self, project_id: str) -> Dict[str, Any]:
        """6 件基座一次性读出，返回 dict 给 context_builder 用"""
        with get_store().connection() as conn:
            wt = conn.execute(
                "SELECT * FROM world_tree WHERE project_id = ?", (project_id,)
            ).fetchone()
            gr = conn.execute(
                "SELECT * FROM genre_resonance WHERE project_id = ?", (project_id,)
            ).fetchone()
            mp = conn.execute(
                "SELECT * FROM main_plot WHERE project_id = ?", (project_id,)
            ).fetchone()
            sps = conn.execute(
                "SELECT * FROM sub_plot WHERE project_id = ?", (project_id,)
            ).fetchall()
            chars = conn.execute(
                "SELECT * FROM characters WHERE project_id = ?", (project_id,)
            ).fetchall()
            rels = conn.execute(
                "SELECT * FROM character_relationships WHERE project_id = ?", (project_id,)
            ).fetchall()
            seeds = conn.execute(
                "SELECT * FROM seeds WHERE project_id = ?", (project_id,)
            ).fetchall()

        return {
            "world_tree": _serialize_world_tree(dict(wt) if wt else {}),
            "genre_resonance": _serialize_genre_resonance(dict(gr) if gr else {}),
            "main_plot": _serialize_main_plot(dict(mp) if mp else {}),
            "sub_plot": _serialize_sub_plot([dict(s) for s in sps]),
            "character_card": _serialize_characters([dict(c) for c in chars], [dict(r) for r in rels]),
            "seed_table": _serialize_seeds([dict(s) for s in seeds]),
        }

    # ----- Character 增量 CRUD -----

    def add_character(self, project_id: str, data: Dict[str, Any]) -> str:
        """新增单个角色，返回 char_id"""
        char_id = data.get("id", f"char-{uuid.uuid4().hex[:8]}")
        with get_store().connection() as conn:
            conn.execute(
                """INSERT INTO characters (
                    id, project_id, name, role, traits_json, speech_style,
                    background, arc, internal_state, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    char_id, project_id,
                    data.get("name", ""), data.get("role", "supporting"),
                    _to_json(data.get("traits", [])),
                    data.get("speech_style"), data.get("background"),
                    data.get("arc"), data.get("internal_state"),
                    _to_json(data.get("metadata", {})), _now(),
                ),
            )
        self.log.info("DB character ADD: project=%s, char_id=%s", project_id, char_id)
        return char_id

    def get_character(self, project_id: str, char_id: str) -> Optional[Dict[str, Any]]:
        """按 char_id 查单个角色，不存在返回 None"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM characters WHERE id = ? AND project_id = ?",
                (char_id, project_id),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["traits"] = _from_json(d.pop("traits_json", None)) or []
        d["metadata"] = _from_json(d.pop("metadata_json", None)) or {}
        return d

    def update_character(self, project_id: str, char_id: str, data: Dict[str, Any]) -> bool:
        """增量更新单个角色（diff merge），返回是否找到"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM characters WHERE id = ? AND project_id = ?",
                (char_id, project_id),
            ).fetchone()
            if not row:
                return False
            old = dict(row)
            conn.execute(
                """UPDATE characters SET
                    name=?, role=?, traits_json=?, speech_style=?,
                    background=?, arc=?, internal_state=?, updated_at=?
                WHERE id=? AND project_id=?""",
                (
                    data.get("name", old["name"]),
                    data.get("role", old["role"]),
                    _to_json(data.get("traits", _from_json(old.get("traits_json")) or [])),
                    data.get("speech_style", old.get("speech_style")),
                    data.get("background", old.get("background")),
                    data.get("arc", old.get("arc")),
                    data.get("internal_state", old.get("internal_state")),
                    _now(), char_id, project_id,
                ),
            )
        self.log.info("DB character UPDATE: project=%s, char_id=%s", project_id, char_id)
        return True

    def delete_character(self, project_id: str, char_id: str) -> None:
        """删除单个角色"""
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM characters WHERE id = ? AND project_id = ?",
                (char_id, project_id),
            )
        self.log.info("DB character DELETE: project=%s, char_id=%s", project_id, char_id)

    # ----- Relationship 增量 CRUD -----

    def add_relationship(self, project_id: str, data: Dict[str, Any]) -> str:
        """新增单个角色关系，返回 rel_id"""
        rel_id = data.get("id", f"rel-{uuid.uuid4().hex[:8]}")
        with get_store().connection() as conn:
            conn.execute(
                """INSERT INTO character_relationships (
                    id, project_id, from_char_id, to_char_id, type,
                    description, evolution_json, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rel_id, project_id,
                    data.get("from_char"), data.get("to_char"),
                    data.get("type"), data.get("description"),
                    _to_json(data.get("evolution", [])),
                    _to_json(data.get("metadata", {})), _now(),
                ),
            )
        self.log.info("DB relationship ADD: project=%s, rel_id=%s", project_id, rel_id)
        return rel_id

    def delete_relationship(self, project_id: str, rel_id: str) -> None:
        """删除单个角色关系"""
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM character_relationships WHERE id = ? AND project_id = ?",
                (rel_id, project_id),
            )
        self.log.info("DB relationship DELETE: project=%s, rel_id=%s", project_id, rel_id)

    # ----- Core Rule（world_tree.core_rules_json 数组操作）-----

    def get_core_rules(self, project_id: str) -> Optional[List[Dict[str, Any]]]:
        """读取 core_rules 列表，world_tree 不存在返回 None"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT core_rules_json FROM world_tree WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        return _from_json(row["core_rules_json"]) or []

    def save_core_rules(self, project_id: str, rules: List[Dict[str, Any]]) -> None:
        """将更新后的 core_rules 写回 world_tree"""
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE world_tree SET core_rules_json = ?, updated_at = ? WHERE project_id = ?",
                (_to_json(rules), _now(), project_id),
            )

    # ----- Timeline / Geography（world_tree 列级更新）-----

    def update_timeline(self, project_id: str, data: Dict[str, Any]) -> bool:
        """更新 world_tree timeline 字段，返回是否找到"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM world_tree WHERE project_id = ?", (project_id,)
            ).fetchone()
            if not row:
                return False
            conn.execute(
                """UPDATE world_tree SET
                    timeline_era=?, anchor_event=?, updated_at=?
                WHERE project_id=?""",
                (
                    data.get("era", row["timeline_era"]),
                    data.get("anchor_event", row["anchor_event"]),
                    _now(), project_id,
                ),
            )
        return True

    def update_geography(self, project_id: str, data: Dict[str, Any]) -> bool:
        """更新 world_tree geography 字段，返回是否找到"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM world_tree WHERE project_id = ?", (project_id,)
            ).fetchone()
            if not row:
                return False
            conn.execute(
                """UPDATE world_tree SET
                    geography_primary=?, geography_secondary_json=?,
                    geography_spatial_rules_json=?, updated_at=?
                WHERE project_id=?""",
                (
                    data.get("primary", row["geography_primary"]),
                    _to_json(data.get("secondary",
                        _from_json(row["geography_secondary_json"]) or [])),
                    _to_json(data.get("spatial_rules",
                        _from_json(row["geography_spatial_rules_json"]) or [])),
                    _now(), project_id,
                ),
            )
        return True

    # ----- Seed 增量 CRUD -----

    def add_seed(self, project_id: str, data: Dict[str, Any]) -> int:
        """新增单颗种子，返回 seed.id（自增主键）"""
        with get_store().connection() as conn:
            cursor = conn.execute(
                """INSERT INTO seeds (
                    project_id, content, name, trigger, payoff,
                    estimated_chapter, payoff_chapter,
                    importance_primary, size, planned_interval,
                    orientation, planted_at_chapter, planted_in_node, planted_context,
                    last_seen_chapter, weight, status, linked_char_ids_json,
                    linked_subplot_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id,
                    data.get("content", ""),
                    data.get("name"),
                    data.get("trigger"),
                    data.get("payoff"),
                    data.get("estimated_chapter"),
                    data.get("payoff_chapter"),
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
                    _to_json(data.get("linked_char_ids", [])),
                    data.get("linked_subplot_id"),
                    _now(),
                ),
            )
        seed_id = cursor.lastrowid
        self.log.info("DB seed ADD: project=%s, seed_id=%s", project_id, seed_id)
        return seed_id

    def update_seed(self, project_id: str, seed_id: int, data: Dict[str, Any]) -> bool:
        """增量更新单颗种子，返回是否找到"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM seeds WHERE id = ? AND project_id = ?",
                (seed_id, project_id),
            ).fetchone()
            if not row:
                return False
            old = dict(row)
            conn.execute(
                """UPDATE seeds SET
                    content=?, name=?, trigger=?, payoff=?,
                    estimated_chapter=?, payoff_chapter=?,
                    importance_primary=?, size=?, planned_interval=?,
                    orientation=?, weight=?, status=?, updated_at=?
                WHERE id=? AND project_id=?""",
                (
                    data.get("content", old["content"]),
                    data.get("name", old.get("name")),
                    data.get("trigger", old.get("trigger")),
                    data.get("payoff", old.get("payoff")),
                    data.get("estimated_chapter", old.get("estimated_chapter")),
                    data.get("payoff_chapter", old.get("payoff_chapter")),
                    data.get("importance_primary", old["importance_primary"]),
                    data.get("size", old["size"]),
                    data.get("planned_interval", old["planned_interval"]),
                    data.get("orientation", old["orientation"]),
                    data.get("weight", old["weight"]),
                    data.get("status", old["status"]),
                    _now(), seed_id, project_id,
                ),
            )
        self.log.info("DB seed UPDATE: project=%s, seed_id=%s", project_id, seed_id)
        return True

    def delete_seed(self, project_id: str, seed_id: int) -> None:
        """删除单颗种子"""
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM seeds WHERE id = ? AND project_id = ?",
                (seed_id, project_id),
            )
        self.log.info("DB seed DELETE: project=%s, seed_id=%s", project_id, seed_id)

    # ----- Subplot 增量 CRUD -----

    def add_subplot(self, project_id: str, data: Dict[str, Any]) -> str:
        """新增单个支线，返回 subplot_id"""
        sp_id = data.get("id", f"subplot-{uuid.uuid4().hex[:8]}")
        with get_store().connection() as conn:
            conn.execute(
                """INSERT INTO sub_plot (
                    id, project_id, title, description, parent_beat_id, status, priority,
                    linked_seeds_json, linked_chars_json, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sp_id, project_id,
                    data.get("title", ""), data.get("description"),
                    data.get("parent_beat_id"),
                    data.get("status", "pending"),
                    data.get("priority", "side"),
                    _to_json(data.get("linked_seeds", [])),
                    _to_json(data.get("linked_chars", [])),
                    _to_json(data.get("metadata", {})),
                    _now(),
                ),
            )
        self.log.info("DB subplot ADD: project=%s, sp_id=%s", project_id, sp_id)
        return sp_id

    def delete_subplot(self, project_id: str, sp_id: str) -> None:
        """删除单个支线"""
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM sub_plot WHERE id = ? AND project_id = ?",
                (sp_id, project_id),
            )
        self.log.info("DB subplot DELETE: project=%s, sp_id=%s", project_id, sp_id)

    # ----- Beat（main_plot.beats_json 数组操作）-----

    def get_beats(self, project_id: str) -> Optional[List[Dict[str, Any]]]:
        """读取 beats 列表，main_plot 不存在返回 None"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT beats_json FROM main_plot WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        return _from_json(row["beats_json"]) or []

    def save_beats(self, project_id: str, beats: List[Dict[str, Any]]) -> None:
        """将更新后的 beats 写回 main_plot"""
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE main_plot SET beats_json = ?, updated_at = ? WHERE project_id = ?",
                (_to_json(beats), _now(), project_id),
            )


# ============ DB → dict 序列化 ============

def _serialize_world_tree(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return {}
    timeline = {}
    if row.get("timeline_era"):
        timeline["era"] = row["timeline_era"]
    if row.get("anchor_event"):
        timeline["anchor_event"] = row["anchor_event"]
    geography = {}
    if row.get("geography_primary"):
        geography["primary"] = row["geography_primary"]
    if row.get("geography_secondary_json"):
        geography["secondary"] = _from_json(row["geography_secondary_json"])
    if row.get("geography_spatial_rules_json"):
        geography["spatial_rules"] = _from_json(row["geography_spatial_rules_json"])
    return {
        "schema_version": row.get("schema_version", "1.0"),
        "base": {
            "timeline": timeline,
            "geography": geography,
            "core_rules": _from_json(row.get("core_rules_json")) or [],
        },
        "metadata": _from_json(row.get("metadata_json")) or {},
    }


def _serialize_genre_resonance(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return {}
    return {
        "schema_version": "1.0",
        "accept": _from_json(row.get("accept_json")) or [],
        "reject": _from_json(row.get("reject_json")) or [],
        "anchors": _from_json(row.get("anchors_json")) or [],
        "metadata": _from_json(row.get("metadata_json")) or {},
    }


def _serialize_main_plot(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return {}
    return {
        "schema_version": "1.0",
        "current_beat": row.get("current_beat", 0),
        "arc_phrase": row.get("arc_phrase"),
        "beats": _from_json(row.get("beats_json")) or [],
        "metadata": _from_json(row.get("metadata_json")) or {},
    }


def _serialize_sub_plot(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    threads = []
    for r in rows:
        threads.append({
            "id": r["id"],
            "title": r.get("title", ""),
            "description": r.get("description"),
            "parent_beat_id": r.get("parent_beat_id"),
            "status": r.get("status"),
            "priority": r.get("priority"),
            "linked_seeds": _from_json(r.get("linked_seeds_json")) or [],
            "linked_chars": _from_json(r.get("linked_chars_json")) or [],
            "metadata": _from_json(r.get("metadata_json")) or {},
        })
    return {"schema_version": "1.0", "threads": threads, "metadata": {}}


def _serialize_characters(chars: List[Dict[str, Any]], rels: List[Dict[str, Any]]) -> Dict[str, Any]:
    characters = []
    for c in chars:
        characters.append({
            "id": c["id"],
            "name": c.get("name", ""),
            "role": c.get("role"),
            "traits": _from_json(c.get("traits_json")) or [],
            "speech_style": c.get("speech_style"),
            "background": c.get("background"),
            "arc": c.get("arc"),
            "internal_state": c.get("internal_state"),
            "metadata": _from_json(c.get("metadata_json")) or {},
        })
    relationships = []
    for r in rels:
        relationships.append({
            "id": r["id"],
            "from_char": r.get("from_char_id"),
            "to_char": r.get("to_char_id"),
            "type": r.get("type"),
            "description": r.get("description"),
            "evolution": _from_json(r.get("evolution_json")) or [],
            "metadata": _from_json(r.get("metadata_json")) or {},
        })
    return {
        "schema_version": "1.0",
        "characters": characters,
        "relationships": relationships,
        "metadata": {},
    }


def _serialize_seeds(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    seeds = []
    for r in rows:
        seeds.append({
            "id": r["id"],
            "content": r.get("content", ""),
            "name": r.get("name"),
            "trigger": r.get("trigger"),
            "payoff": r.get("payoff"),
            "estimated_chapter": r.get("estimated_chapter"),
            "payoff_chapter": r.get("payoff_chapter"),
            "importance": {"primary": r.get("importance_primary")},
            "size": r.get("size"),
            "planned_interval": r.get("planned_interval"),
            "orientation": r.get("orientation"),
            "planted_at_chapter": r.get("planted_at_chapter", 0),
            "planted_in_node": r.get("planted_in_node"),
            "planted_context": r.get("planted_context"),
            "last_seen_chapter": r.get("last_seen_chapter", 0),
            "weight": r.get("weight", 0.5),
            "status": r.get("status"),
            "linked_char_ids": _from_json(r.get("linked_char_ids_json")) or [],
            "linked_subplot_id": r.get("linked_subplot_id"),
        })
    return {"schema_version": "1.0", "seeds": seeds, "metadata": {}}
