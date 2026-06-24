"""ChapterRepository — chapters + chapter_seed_changes + chapter_character_states

v0.4.1 落地：章节 metadata 入 DB，正文留文件
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from backend.persistence.models import ChapterRow
from backend.persistence.sqlite_store import get_store
from backend.utils.logger import logger


def _now() -> datetime:
    return datetime.now()


@logger
class ChapterRepository:
    """chapters 表 + 关联表"""

    # ----- chapters CRUD -----

    def create(
        self,
        project_id: str,
        chapter_num: int,
        file_path: str,
        title: Optional[str] = None,
        content_text: Optional[str] = None,
        word_count: int = 0,
        intervention: Optional[str] = None,
        actor_feedback: Optional[str] = None,
        actor_character: Optional[str] = None,
        summary: Optional[str] = None,
        detailed_summary: Optional[str] = None,
    ) -> ChapterRow:
        """创建章节（metadata 落 DB + 正文写文件）"""
        now = _now()
        if content_text is not None and file_path:
            # 正文落文件
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            Path(file_path).write_text(content_text, encoding="utf-8")
            word_count = word_count or len(content_text)
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO chapters (
                    project_id, chapter_num, title, summary, detailed_summary, word_count,
                    file_path, intervention, actor_feedback, actor_character,
                    generated_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id, chapter_num, title, summary, detailed_summary, word_count,
                    file_path, intervention, actor_feedback, actor_character,
                    now, now,
                ),
            )
        self.log.info("DB chapter CREATE: project=%s, num=%d, title=%r, word_count=%d",
                 project_id, chapter_num, title, word_count)
        return ChapterRow(
            project_id=project_id, chapter_num=chapter_num, title=title,
            summary=summary, detailed_summary=detailed_summary, word_count=word_count,
            file_path=file_path, intervention=intervention, actor_feedback=actor_feedback,
            actor_character=actor_character, generated_at=now, updated_at=now,
        )

    def get(self, project_id: str, chapter_num: int) -> Optional[ChapterRow]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM chapters WHERE project_id = ? AND chapter_num = ?",
                (project_id, chapter_num),
            ).fetchone()
        if not row:
            return None
        return ChapterRow(**dict(row))

    def list_by_project(self, project_id: str, limit: int = 100) -> List[ChapterRow]:
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM chapters WHERE project_id = ? "
                "ORDER BY chapter_num DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [ChapterRow(**dict(r)) for r in rows]

    def get_latest(self, project_id: str) -> Optional[ChapterRow]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM chapters WHERE project_id = ? ORDER BY chapter_num DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        return ChapterRow(**dict(row))

    def update_summary(
        self,
        project_id: str,
        chapter_num: int,
        summary: Optional[str] = None,
        detailed_summary: Optional[str] = None,
    ) -> None:
        """更新 summary（章节生成后同步抽 summary / 每 20 章异步生成 detailed_summary）"""
        with get_store().connection() as conn:
            if summary is not None and detailed_summary is not None:
                conn.execute(
                    "UPDATE chapters SET summary = ?, detailed_summary = ?, updated_at = ? "
                    "WHERE project_id = ? AND chapter_num = ?",
                    (summary, detailed_summary, _now(), project_id, chapter_num),
                )
            elif summary is not None:
                conn.execute(
                    "UPDATE chapters SET summary = ?, updated_at = ? "
                    "WHERE project_id = ? AND chapter_num = ?",
                    (summary, _now(), project_id, chapter_num),
                )
            elif detailed_summary is not None:
                conn.execute(
                    "UPDATE chapters SET detailed_summary = ?, updated_at = ? "
                    "WHERE project_id = ? AND chapter_num = ?",
                    (detailed_summary, _now(), project_id, chapter_num),
                )

    def update_intervention(
        self,
        project_id: str,
        chapter_num: int,
        intervention: Optional[str] = None,
        actor_feedback: Optional[str] = None,
        actor_character: Optional[str] = None,
    ) -> None:
        """更新章节干预字段（InterventionParser 调用）"""
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE chapters SET intervention = ?, actor_feedback = ?, actor_character = ?, updated_at = ? "
                "WHERE project_id = ? AND chapter_num = ?",
                (intervention or "", actor_feedback or "", actor_character or "",
                 _now(), project_id, chapter_num),
            )

    def delete(self, project_id: str, chapter_num: int) -> None:
        """删除章节（cascade 删关联表）"""
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM chapters WHERE project_id = ? AND chapter_num = ?",
                (project_id, chapter_num),
            )
        self.log.info("DB chapter DELETE: project=%s, num=%d", project_id, chapter_num)

    def rollback_to(self, project_id: str, to_chapter: int) -> int:
        """回档到指定章节：删 > to_chapter 的所有章节（cascade 删关联表）。返回删除数"""
        with get_store().connection() as conn:
            cursor = conn.execute(
                "DELETE FROM chapters WHERE project_id = ? AND chapter_num > ?",
                (project_id, to_chapter),
            )
            removed = cursor.rowcount
        self.log.info("DB chapter ROLLBACK: project=%s, to_chapter=%d, removed=%d", project_id, to_chapter, removed)
        return removed

    def count_chapters(self, project_id: str) -> int:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM chapters WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return row["c"]

    # ----- chapter_seed_changes 关联表 -----

    def record_seed_change(
        self,
        project_id: str,
        chapter_num: int,
        seed_id: int,
        change_type: str,  # planted / resonating / harvested
        context: Optional[str] = None,
    ) -> None:
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO chapter_seed_changes (
                    project_id, chapter_num, seed_id, change_type, context, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, chapter_num, seed_id, change_type, context, _now()),
            )

    def list_seed_changes(self, project_id: str, chapter_num: int) -> List[Dict[str, Any]]:
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM chapter_seed_changes WHERE project_id = ? AND chapter_num = ?",
                (project_id, chapter_num),
            ).fetchall()
        return [dict(r) for r in rows]

    # ----- chapter_character_states 关联表 -----

    def record_character_state(
        self,
        project_id: str,
        chapter_num: int,
        character_id: str,
        state_text: Optional[str] = None,
    ) -> None:
        """upsert（同一 chapter_num + character_id 只能有一个状态）"""
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO chapter_character_states (
                    project_id, chapter_num, character_id, state_text, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id, chapter_num, character_id) DO UPDATE SET
                    state_text=excluded.state_text,
                    updated_at=excluded.updated_at
                """,
                (project_id, chapter_num, character_id, state_text, _now()),
            )

    def list_character_states(self, project_id: str, chapter_num: int) -> List[Dict[str, Any]]:
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM chapter_character_states WHERE project_id = ? AND chapter_num = ?",
                (project_id, chapter_num),
            ).fetchall()
        return [dict(r) for r in rows]
