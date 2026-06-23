"""AsyncChapterGenerator — 异步章节生成器

职责：委托 state_graph_stub 生成小说章节
"""
from __future__ import annotations

from pathlib import Path


class AsyncChapterGenerator:
    """v0.4 章节生成占位（v0.4.1 不变，仍委托给 state_graph_stub）"""

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)

    async def generate_chapter(
        self,
        project_id: str,
        intervention: str | None = None,
        actor_feedback: str | None = None,
        actor_character: str | None = None,
    ) -> dict:
        """委托给 state_graph_stub.generate_chapter_via_state_graph（DB-aware）"""
        from backend.agent.state_graph_stub import generate_chapter_via_state_graph
        return await generate_chapter_via_state_graph(
            project_id=project_id,
            intervention=intervention,
            actor_feedback=actor_feedback,
            actor_character=actor_character,
        )

