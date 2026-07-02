"""ProjectManager：项目 CRUD + 软删除 + 回档 + trash 恢复"""
from __future__ import annotations

import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from backend.persistence import (
    ProjectRepository, ChapterRepository,
    ChapterStatusRepository, OnboardingRepository,
)
from backend.utils.logger import logger


@logger
class ProjectManager:
    """异步项目管理器"""

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)
        self.projects_root = Path(workspace_root) / "projects"
        self.chapters_root = self.projects_root
        self.trash_root = self.projects_root / ".trash"
        self._proj_repo = ProjectRepository()
        self._chap_repo = ChapterRepository()

    # ============ CRUD ============

    async def create(self, name: str, initial_prompt: Optional[str] = None,
                    exploration_level: str = "standard") -> dict:
        """创建项目（DB + 目录）"""
        import secrets
        project_id = f"world-{secrets.token_hex(4)}"
        self.log.info("PM create START: name=%r, exploration_level=%s, id=%s", name, exploration_level, project_id)
        project = self._proj_repo.create(
            project_id=project_id, name=name,
            exploration_level=exploration_level,
        )
        project_path = self.projects_root / project_id
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "chapters").mkdir(parents=True, exist_ok=True)
        self.log.info("PM create DONE: id=%s, path=%s", project_id, project_path)
        return {
            "id": project.id,
            "name": project.name,
            "exploration_level": project.exploration_level,
        }

    async def update_exploration_level(
        self, project_id: str, exploration_level: str
    ) -> None:
        """切换探索度 (conservative/standard/wild)"""
        project = self._proj_repo.get(project_id)
        if project is None:
            raise FileNotFoundError(f"Project not found: {project_id}")
        self._proj_repo.update_exploration_level(project_id, exploration_level)

    async def load(self, project_id: str) -> Optional[dict]:
        """加载项目详情（DB 优先）

        过滤已软删项目（deleted_at 非空）
        """
        project = self._proj_repo.get(project_id)
        if not project:
            return None
        # 软删项目不允许 load
        if hasattr(project, "deleted_at") and project.deleted_at is not None:
            self.log.info("PM.load: project=%s 已软删 (deleted_at=%s), 返回 None",
                          project_id, project.deleted_at)
            return None
        all_artifacts = self._proj_repo.load_all_artifacts(project_id)
        chapter_rows = self._chap_repo.list_by_project(project_id, limit=200)
        chapters = []
        for c in chapter_rows:
            chapters.append({
                "num": c.chapter_num,
                "title": c.title or f"第 {c.chapter_num} 章",
                "summary": c.summary,
                "word_count": c.word_count,
                "file_path": c.file_path,
            })
        onboarding_step = None
        onboarding_payload: dict = {}
        try:
            ob_row = OnboardingRepository().get(project_id)
            if ob_row:
                onboarding_step = ob_row.current_step
                try:
                    import json as _json
                    state_data = _json.loads(ob_row.state_json)
                    onboarding_payload = state_data.get("payload", {}) or {}
                except Exception:
                    pass
        except Exception:
            pass
        # current_pov 存 char_id，查 name 供前端展示（复用已有 project 对象，避免重复查 DB）
        pov_char_id = project.current_pov
        pov_char_name: Optional[str] = None
        if pov_char_id:
            char = self._proj_repo.get_character(project.id, pov_char_id)
            if char:
                pov_char_name = char.get("name")
            else:
                # 兼容旧数据：char_id 查不到角色，说明存的是 name 字符串
                pov_char_name = pov_char_id

        return {
            "id": project.id,
            "name": project.name,
            "exploration_level": project.exploration_level,
            "current_pov": pov_char_id,
            "current_pov_char_id": pov_char_id,
            "current_pov_name": pov_char_name,
            "cover_image_url": project.cover_image_url,
            "onboarding_step": onboarding_step,
            "onboarding_payload": onboarding_payload,
            "seven_artifacts": all_artifacts,
            "world_tree": all_artifacts.get("world_tree", {}),
            "chapters": chapters,
        }

    async def list_projects(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """列项目"""
        projects = self._proj_repo.list_all(limit=limit + offset)
        onboarding_map: dict[str, int] = {}
        try:
            onboarding_map = OnboardingRepository().list_current_steps()
        except Exception:
            pass

        result = []
        for p in projects[offset:]:
            chapter_count = self._chap_repo.count_chapters(p.id)
            onboarding_step = onboarding_map.get(p.id)
            result.append({
                "id": p.id,
                "name": p.name,
                "exploration_level": p.exploration_level,
                "chapter_count": chapter_count,
                "onboarding_step": onboarding_step,
                "cover_image_url": p.cover_image_url,
                "status": "completed" if chapter_count > 0 else (
                    "in_progress" if onboarding_step else "not_started"
                ),
                "last_updated": p.updated_at.isoformat() if p.updated_at else None,
            })
        return result

    async def update_base(
        self,
        project_id: str,
        key: str,
        new_value: str,
    ) -> dict:
        """改 6 件基座（整段写入）"""
        import json
        try:
            parsed = json.loads(new_value)
        except Exception:
            parsed = new_value

        key_to_table = {
            "world_tree": "world_tree",
            "genre_resonance": "genre_resonance",
            "main_plot": "main_plot",
            "sub_plot": "sub_plot",
            "character_card": None,
            "seed_table": "seeds",
        }
        table = key_to_table.get(key)
        old_preview = ""
        if table:
            try:
                old_data = self._load_one(project_id, key)
                old_preview = str(old_data)[:100]
            except Exception:
                pass

        world_tree = parsed if key == "world_tree" else self._load_one(project_id, "world_tree")
        genre_resonance = parsed if key == "genre_resonance" else self._load_one(project_id, "genre_resonance")
        main_plot = parsed if key == "main_plot" else self._load_one(project_id, "main_plot")
        sub_plot = parsed if key == "sub_plot" else self._load_one(project_id, "sub_plot")
        character_card = parsed if key == "character_card" else self._load_one(project_id, "character_card")
        seed_table = parsed if key == "seed_table" else self._load_one(project_id, "seed_table")

        self._proj_repo.save_7_artifacts(
            project_id=project_id,
            world_tree=world_tree,
            genre_resonance=genre_resonance,
            main_plot=main_plot,
            sub_plot=sub_plot,
            character_card=character_card,
            seed_table=seed_table,
        )

        chapters = self._chap_repo.list_by_project(project_id, limit=200)
        affected = [c.chapter_num for c in chapters]
        return {
            "project_id": project_id,
            "key": key,
            "old_value_preview": old_preview,
            "new_value_preview": new_value[:100],
            "chapters_affected": affected,
        }

    def _load_one(self, project_id: str, key: str) -> Dict[str, Any]:
        """从 DB 读 6 件之一"""
        all_data = self._proj_repo.load_all_artifacts(project_id)
        return all_data.get(key, {})

    async def rollback(self, project_id: str, to_chapter: int, confirm: bool = False) -> dict:
        """回档到指定章节（cascade 删 chapters + 关联表 + 文件）"""
        if not confirm:
            raise ValueError("rollback requires confirm=True")
        self.log.warning("PM rollback START: project=%s, to_chapter=%d", project_id, to_chapter)
        kept = self._chap_repo.count_chapters(project_id)
        removed = self._chap_repo.rollback_to(project_id, to_chapter)
        kept = kept - removed
        ChapterStatusRepository().delete_after_chapter(project_id, to_chapter)
        project_path = self.projects_root / project_id
        chapters_dir = project_path / "chapters"
        if chapters_dir.exists():
            for f in chapters_dir.glob("chapter_*.md"):
                try:
                    num = int(f.stem.split("_")[1])
                    if num > to_chapter:
                        f.unlink()
                except (ValueError, IndexError):
                    continue
        self.log.warning("PM rollback DONE: project=%s, kept=%d, removed=%d", project_id, kept, removed)
        return {
            "project_id": project_id,
            "to_chapter": to_chapter,
            "kept_chapters": kept,
            "removed_chapters": removed,
        }

    async def soft_delete(self, project_id: str, confirm: bool = False) -> dict:
        """软删除（v003：仅标记 projects.deleted_at，不写 projects_deleted 表）"""
        self.log.warning("PM soft_delete START: project=%s", project_id)
        result = await self.delete(project_id, confirm=confirm)
        self.log.warning("PM soft_delete DONE: project=%s, trash=%s", project_id, result.get("trash_path"))
        return result

    async def delete(self, project_id: str, confirm: bool = False) -> dict:
        """删除项目（mv 到 trash + 软标记 + hard delete）
        
        文件目录不存在时只清 DB。
        """
        if not confirm:
            raise ValueError("delete requires confirm=True")
        self.log.warning("PM delete START: project=%s", project_id)
        project_path = self.projects_root / project_id
        trash_path = ""
        if project_path.exists():
            self.trash_root.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            trash_path = str(self.trash_root / f"{project_id}-{timestamp}")
            await asyncio.to_thread(shutil.move, str(project_path), trash_path)
        self._proj_repo.soft_delete(project_id)
        self._proj_repo.hard_delete(project_id)
        return {
            "project_id": project_id,
            "trash_path": trash_path,
            "deleted_at": datetime.now().isoformat(),
        }

    async def restore(self, trash_name: str) -> dict:
        """从 trash 恢复"""
        trash_path = self.trash_root / trash_name
        if not trash_path.exists():
            raise FileNotFoundError(f"Trash not found: {trash_name}")
        project_id = trash_name.rsplit("-", 1)[0] if "-" in trash_name else trash_name
        target = self.projects_root / project_id
        if target.exists():
            raise FileExistsError(f"Project {project_id} already exists")
        await asyncio.to_thread(shutil.move, str(trash_path), str(target))
        self._proj_repo.restore_delete(project_id)
        return {"project_id": project_id, "restored_from": str(trash_path)}

