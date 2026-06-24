"""ProjectDeletedRepository: projects_deleted 表的 CRUD

v1.3 软删方案 b
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.persistence.models import ProjectDeleted
from backend.persistence.sqlite_store import get_store


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

