"""AsyncInterventionParser — 异步剧情干预解析器

职责：将用户的干预指令写入最新章节的 intervention 字段
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


class AsyncInterventionParser:

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)

    async def add(
        self,
        project_id: str,
        intervention: str | None = None,
        actor_feedback: str | None = None,
        actor_character: str | None = None,
    ) -> dict:
        """写干预到下一章（最新章节的 intervention 字段）"""
        from backend.persistence import ChapterRepository
        chap_repo = ChapterRepository()
        latest = chap_repo.get_latest(project_id)
        if not latest:
            # 还没有章节，新建一个空槽位
            return {
                "project_id": project_id,
                "accepted": False,
                "reason": "no chapter yet",
            }
        # 更新最新章节的 intervention
        from backend.persistence import get_store
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE chapters SET intervention = ?, actor_feedback = ?, actor_character = ?, updated_at = ? "
                "WHERE project_id = ? AND chapter_num = ?",
                (intervention or "", actor_feedback or "", actor_character or "",
                 datetime.now(), project_id, latest.chapter_num),
            )
        return {
            "project_id": project_id,
            "chapter_num": latest.chapter_num,
            "accepted": True,
        }

