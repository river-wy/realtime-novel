"""ChapterRepository — chapters 表

v003 重构（spec: .spec/db-refactor/spec.md）
- 删除：actor_feedback / actor_character / detailed_summary / chapter_seed_changes / chapter_character_states
- 新增：volume_id 关联字段
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, List

from backend.persistence.models import ChapterRow
from backend.persistence.sqlite_store import get_store
from backend.utils.logger import logger


def _now() -> datetime:
    return datetime.now()


@logger
class ChapterRepository:
    """chapters 表 CRUD"""

    def create(
        self,
        project_id: str,
        chapter_num: int,
        file_path: str,
        title: Optional[str] = None,
        content_text: Optional[str] = None,
        word_count: int = 0,
        intervention: Optional[str] = None,
        summary: Optional[str] = None,
        volume_id: Optional[str] = None,
    ) -> ChapterRow:
        """创建章节（metadata 落 DB + 正文写文件）

        v003：删 actor_feedback / actor_character / detailed_summary 入参
        v003：新增 volume_id 入参
        """
        now = _now()
        if content_text is not None and file_path:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            Path(file_path).write_text(content_text, encoding="utf-8")
            word_count = word_count or len(content_text)
        with get_store().connection() as conn:
            conn.execute(
                """
                INSERT INTO chapters (
                    project_id, chapter_num, volume_id, title, summary, word_count,
                    file_path, intervention, generated_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id, chapter_num, volume_id, title, summary, word_count,
                    file_path, intervention, now, now,
                ),
            )
        self.log.info(
            "DB chapter CREATE: project=%s, num=%d, title=%r, word_count=%d",
            project_id, chapter_num, title, word_count,
        )
        return ChapterRow(
            project_id=project_id, chapter_num=chapter_num, volume_id=volume_id,
            title=title, summary=summary, word_count=word_count,
            file_path=file_path, intervention=intervention,
            generated_at=now, updated_at=now,
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
    ) -> None:
        """更新 summary（章节生成后同步）

        v003：删 detailed_summary 参数
        """
        with get_store().connection() as conn:
            if summary is not None:
                conn.execute(
                    "UPDATE chapters SET summary = ?, updated_at = ? "
                    "WHERE project_id = ? AND chapter_num = ?",
                    (summary, _now(), project_id, chapter_num),
                )

    def update_intervention(
        self,
        project_id: str,
        chapter_num: int,
        intervention: Optional[str] = None,
    ) -> None:
        """更新章节干预字段（InterventionParser 调用）

        v003：删 actor_feedback / actor_character 入参
        """
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE chapters SET intervention = ?, updated_at = ? "
                "WHERE project_id = ? AND chapter_num = ?",
                (intervention or "", _now(), project_id, chapter_num),
            )

    def delete(self, project_id: str, chapter_num: int) -> None:
        """删除章节"""
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM chapters WHERE project_id = ? AND chapter_num = ?",
                (project_id, chapter_num),
            )
        self.log.info("DB chapter DELETE: project=%s, num=%d", project_id, chapter_num)

    def rollback_to(self, project_id: str, to_chapter: int) -> int:
        """回档到指定章节：删 > to_chapter 的所有章节"""
        with get_store().connection() as conn:
            cursor = conn.execute(
                "DELETE FROM chapters WHERE project_id = ? AND chapter_num > ?",
                (project_id, to_chapter),
            )
            removed = cursor.rowcount
        self.log.info(
            "DB chapter ROLLBACK: project=%s, to_chapter=%d, removed=%d",
            project_id, to_chapter, removed,
        )
        return removed

    def count_chapters(self, project_id: str) -> int:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM chapters WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return row["c"]
