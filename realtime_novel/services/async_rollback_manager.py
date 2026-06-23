"""AsyncRollbackManager — 异步回档管理器

职责：委托 AsyncProjectManager 执行章节回档操作
"""
from __future__ import annotations

from pathlib import Path


class AsyncRollbackManager:
    """rollback 委托"""

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)

    async def rollback(
        self, project_id: str, to_chapter: int, confirm: bool = False
    ) -> dict:
        from realtime_novel.services.async_project_manager import AsyncProjectManager
        pm = AsyncProjectManager(workspace_root=self.workspace_root)
        return await pm.rollback(project_id, to_chapter, confirm=confirm)

