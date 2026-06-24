"""ChapterStatusRepository: chapter_status 表的 CRUD

对应 spec.md §4.1

ProjectDeletedRepository 已迁移到 project_deleted_repository.py
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.persistence.models import ChapterStatus, ChapterState
from backend.persistence.sqlite_store import get_store


class ChapterStatusRepository:
    """章节状态 Repository（v0.4 从文件迁入 SQLite）"""

    async def set_status(
        self,
        project_id: str,
        chapter_num: int,
        status: ChapterState | str,
        error: Optional[str] = None,
    ) -> ChapterStatus:
        """设置章节状态（自动设置 started_at/completed_at）"""
        state = ChapterState(status) if isinstance(status, str) else status
        now = datetime.now()
        started_at = now if state in (ChapterState.GENERATING, ChapterState.DONE, ChapterState.FAILED) else None
        completed_at = now if state in (ChapterState.DONE, ChapterState.FAILED) else None

        with get_store().connection() as conn:
            # 查旧值保留 started_at
            row = conn.execute(
                "SELECT started_at FROM chapter_status WHERE project_id = ? AND chapter_num = ?",
                (project_id, chapter_num),
            ).fetchone()
            old_started = row["started_at"] if row else None
            final_started = old_started or started_at

            conn.execute(
                """INSERT INTO chapter_status (project_id, chapter_num, status, started_at, completed_at, error)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(project_id, chapter_num) DO UPDATE SET
                     status = excluded.status,
                     completed_at = excluded.completed_at,
                     error = excluded.error""",
                (project_id, chapter_num, state.value, final_started, completed_at, error),
            )
        return ChapterStatus(
            project_id=project_id, chapter_num=chapter_num, status=state,
            started_at=final_started, completed_at=completed_at, error=error,
        )

    async def get_status(self, project_id: str, chapter_num: int) -> Optional[ChapterStatus]:
        """查询章节状态"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM chapter_status WHERE project_id = ? AND chapter_num = ?",
                (project_id, chapter_num),
            ).fetchone()
        if not row:
            return None
        return ChapterStatus(
            project_id=row["project_id"],
            chapter_num=row["chapter_num"],
            status=ChapterState(row["status"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error=row["error"],
        )

    async def delete_by_project(self, project_id: str) -> int:
        """删除项目所有章节状态（用于 rollback / 项目删除）"""
        with get_store().connection() as conn:
            cursor = conn.execute(
                "DELETE FROM chapter_status WHERE project_id = ?", (project_id,)
            )
        return cursor.rowcount

    def delete_after_chapter(self, project_id: str, keep_up_to: int) -> int:
        """删除 chapter_num > keep_up_to 的状态记录（用于回档）

        同步版本，因为 rollback 流程是同步调用。
        """
        with get_store().connection() as conn:
            cursor = conn.execute(
                "DELETE FROM chapter_status WHERE project_id = ? AND chapter_num > ?",
                (project_id, keep_up_to),
            )
        return cursor.rowcount
