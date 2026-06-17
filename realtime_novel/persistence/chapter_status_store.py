"""ChapterStatusRepository: chapter_status 表 + ProjectDeleted 软删除

对应 spec.md §4.1 + v1.3 软删方案 b
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from realtime_novel.persistence.models import ChapterStatus, ChapterState, ProjectDeleted
from realtime_novel.persistence.sqlite_store import get_store


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


class ProjectDeletedRepository:
    """软删除项目 Repository（v1.3 方案 b）"""

    async def add(
        self,
        project_id: str,
        original_name: str,
        palette: str,
        trash_path: str,
    ) -> ProjectDeleted:
        """记录软删除项目"""
        deleted = ProjectDeleted(
            project_id=project_id,
            original_name=original_name,
            palette=palette,
            deleted_at=datetime.now(),
            trash_path=trash_path,
        )
        with get_store().connection() as conn:
            conn.execute(
                "INSERT INTO projects_deleted (project_id, original_name, palette, deleted_at, trash_path) "
                "VALUES (?, ?, ?, ?, ?)",
                (deleted.project_id, deleted.original_name, deleted.palette,
                 deleted.deleted_at, deleted.trash_path),
            )
        return deleted

    async def list_recent(self, limit: int = 100) -> list[ProjectDeleted]:
        """列出最近删除的项目（按 deleted_at DESC）"""
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM projects_deleted ORDER BY deleted_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            ProjectDeleted(
                project_id=r["project_id"],
                original_name=r["original_name"],
                palette=r["palette"],
                deleted_at=r["deleted_at"],
                trash_path=r["trash_path"],
            )
            for r in rows
        ]

    async def list_older_than(self, days: int = 7) -> list[ProjectDeleted]:
        """列出超过 N 天的软删项目（清理用）"""
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM projects_deleted WHERE deleted_at < datetime('now', ?)",
                (f"-{days} days",),
            ).fetchall()
        return [
            ProjectDeleted(
                project_id=r["project_id"],
                original_name=r["original_name"],
                palette=r["palette"],
                deleted_at=r["deleted_at"],
                trash_path=r["trash_path"],
            )
            for r in rows
        ]

    async def remove(self, project_id: str) -> None:
        """清理软删记录（trash 文件 rm 之后调用）"""
        with get_store().connection() as conn:
            conn.execute("DELETE FROM projects_deleted WHERE project_id = ?", (project_id,))
