"""ChapterGenerator — 章节生成器

职责：委托 state_graph_stub 生成小说章节
"""
from __future__ import annotations

from pathlib import Path

from backend.utils.logger import logger


@logger
class ChapterGenerator:
    """章节生成（委托 state_graph_stub）"""

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
        import time
        self.log.info("ChapterGen START: project=%s, intervention=%s, actor=%s",
                 project_id, bool(intervention), bool(actor_character))
        t0 = time.monotonic()
        from backend.agent.state_graph_stub import generate_chapter_via_state_graph
        result = await generate_chapter_via_state_graph(
            project_id=project_id,
            intervention=intervention,
            actor_feedback=actor_feedback,
            actor_character=actor_character,
        )
        self.log.info("ChapterGen DONE: project=%s, num=%s, title=%r, word_count=%s, elapsed=%.1fs",
                 project_id, result.get("num"), result.get("title"),
                 result.get("word_count"), time.monotonic() - t0)
        return result

