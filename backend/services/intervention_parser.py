"""InterventionParser — 剧情干预解析器

v003 重构：删 actor_feedback / actor_character 入参
"""
from __future__ import annotations

from pathlib import Path


class InterventionParser:

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)

    async def add(
        self,
        project_id: str,
        intervention: str | None = None,
    ) -> dict:
        """写干预到下一章（最新章节的 intervention 字段）

        v003：删 actor_feedback / actor_character 入参
        """
        from backend.persistence import ChapterRepository
        chap_repo = ChapterRepository()
        latest = chap_repo.get_latest(project_id)
        if not latest:
            return {
                "project_id": project_id,
                "accepted": False,
                "reason": "no chapter yet",
            }
        # 更新最新章节的 intervention
        chap_repo.update_intervention(
            project_id=project_id,
            chapter_num=latest.chapter_num,
            intervention=intervention,
        )
        return {
            "project_id": project_id,
            "chapter_num": latest.chapter_num,
            "accepted": True,
        }
