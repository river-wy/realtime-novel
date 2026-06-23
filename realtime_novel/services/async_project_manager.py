"""AsyncProjectManager — 异步项目管理器（DB 优先）

职责：项目的 CRUD + 软删除 + 回档 + trash 恢复
"""
from __future__ import annotations

import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from realtime_novel.persistence import (
    ProjectRepository, ChapterRepository, get_store,
    ProjectDeletedRepository,
)


class AsyncProjectManager:
    """ 异步项目管理器 """

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)
        self.projects_root = Path(workspace_root) / "projects"
        self.chapters_root = self.projects_root  # 章节文件路径统一在 projects/{id}/chapters/
        self.trash_root = self.projects_root / ".trash"
        self._proj_repo = ProjectRepository()
        self._chap_repo = ChapterRepository()

    # ============ CRUD ============

    async def create(self, name: str, palette: str, initial_prompt: Optional[str] = None,
                    exploration_level: str = "standard") -> dict:
        """创建项目（projects 表 + 项目目录）
        Args:
            name: 项目名 (人类可读, 中文/英文都可)
            palette: 调色板
        """
        # id 自动生成, 与 name 分离
        import secrets
        project_id = f"world-{secrets.token_hex(4)}"  # 8 字符 hex, 例 world-3f7a8b2c
        # 1. DB 落项目 (v0.8: 传 exploration_level)
        project = self._proj_repo.create(
            project_id=project_id, name=name, palette=palette,
            exploration_level=exploration_level,
        )
        # 2. 创建项目目录（章节文件根）
        project_path = self.projects_root / project_id
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "chapters").mkdir(parents=True, exist_ok=True)
        return {
            "id": project.id,
            "name": project.name,
            "palette": project.palette,
            "exploration_level": project.exploration_level,
        }

    async def load(self, project_id: str) -> Optional[dict]:
        """加载项目（DB 优先）"""
        project = self._proj_repo.get(project_id)
        if not project:
            return None
        # 7 件基座（DB 读）
        all_artifacts = self._proj_repo.load_all_artifacts(project_id)
        # 章节列表（DB 读 metadata，正文按 file_path 拼）
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
        # 读 onboarding_state.current_step (项目从哪一步开始续接)
        onboarding_step = None
        try:
            from realtime_novel.persistence.sqlite_store import get_store
            with get_store().connection() as conn:
                row = conn.execute(
                    "SELECT current_step FROM onboarding_state WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
            if row:
                onboarding_step = int(row["current_step"])
        except Exception:
            pass
        return {
            "id": project.id,
            "name": project.name,
            "palette": project.palette,
            "exploration_level": project.exploration_level,  # v0.8
            "current_pov": project.current_pov,
            "onboarding_step": onboarding_step,  # 0=未开始, 1-4=进行中, None=已加载
            "seven_artifacts": all_artifacts,  # 兼容旧字段名
            "world_tree": all_artifacts.get("world_tree", {}),
            "chapters": chapters,
        }

    async def list_projects(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """列项目（DB 优先）"""
        from realtime_novel.persistence.sqlite_store import get_store

        projects = self._proj_repo.list_all(limit=limit + offset)
        # v0.8.3: 一次查所有 onboarding_state (避免 N+1)
        onboarding_map: dict[str, int] = {}
        try:
            with get_store().connection() as conn:
                rows = conn.execute(
                    "SELECT project_id, current_step FROM onboarding_state"
                ).fetchall()
            for r in rows:
                try:
                    onboarding_map[r["project_id"]] = int(r["current_step"])
                except Exception:
                    pass
        except Exception:
            pass

        result = []
        for p in projects[offset:]:
            # 章节数从 DB 读
            chapter_count = self._chap_repo.count_chapters(p.id)
            onboarding_step = onboarding_map.get(p.id)  # None=从未进过, 0=未开始, 1-4=进行中
            result.append({
                "id": p.id,
                "name": p.name,
                "palette": p.palette,
                "exploration_level": p.exploration_level,  # v0.8
                "chapter_count": chapter_count,
                "onboarding_step": onboarding_step,  # v0.8.3: 续接用
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
        """改 7 件基座（spec §6.1 PATCH /base）

        兼容旧 API：`new_value: str` 整段写入。
        v0.4.1 推荐改用 `update_artifact`（结构化）。
        """
        # 兼容路径：把 str 当作整段 JSON/YAML 写入对应表
        import json
        try:
            parsed = json.loads(new_value)
        except Exception:
            parsed = new_value  # 字符串原样存

        # 7 件表名映射（v0.4 key 名 → v0.4.1 表名）
        key_to_table = {
            "world_tree": "world_tree",
            "style_charter": "style_charter",
            "genre_resonance": "genre_resonance",
            "main_plot": "main_plot",
            "sub_plot": "sub_plot",
            "character_card": None,  # 跨 characters + character_relationships
            "seed_table": "seeds",
        }
        table = key_to_table.get(key)
        old_preview = ""
        if table:
            with get_store().connection() as conn:
                row = conn.execute(
                    f"SELECT * FROM {table} WHERE project_id = ?", (project_id,)
                ).fetchone()
                if row:
                    old_preview = str(dict(row))[:100]

        # 读其他 6 件保持不变
        world_tree = parsed if key == "world_tree" else self._load_one(project_id, "world_tree")
        style_charter = parsed if key == "style_charter" else self._load_one(project_id, "style_charter")
        genre_resonance = parsed if key == "genre_resonance" else self._load_one(project_id, "genre_resonance")
        main_plot = parsed if key == "main_plot" else self._load_one(project_id, "main_plot")
        sub_plot = parsed if key == "sub_plot" else self._load_one(project_id, "sub_plot")
        character_card = parsed if key == "character_card" else self._load_one(project_id, "character_card")
        seed_table = parsed if key == "seed_table" else self._load_one(project_id, "seed_table")

        self._proj_repo.save_7_artifacts(
            project_id=project_id,
            world_tree=world_tree,
            style_charter=style_charter,
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
        """从 DB 读 7 件之一（dict 形式）"""
        all_data = self._proj_repo.load_all_artifacts(project_id)
        # v0.8.2: load_all_artifacts 已用正常 key (无 .yaml 后缀), 直接返即可
        return all_data.get(key, {})

    async def rollback(self, project_id: str, to_chapter: int, confirm: bool = False) -> dict:
        """回档到指定章节（cascade 删 chapters + 关联表）

        返回 {kept_chapters, removed_chapters}
        """
        if not confirm:
            raise ValueError("rollback requires confirm=True")
        # DB cascade 删章节 metadata + 关联表
        kept = self._chap_repo.count_chapters(project_id)
        removed = self._chap_repo.rollback_to(project_id, to_chapter)
        kept = kept - removed
        # 同步 chapter_status 表
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM chapter_status WHERE project_id = ? AND chapter_num > ?",
                (project_id, to_chapter),
            )
        # 文件系统清理：删 > to_chapter 的 chapter_NNN.md
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
        return {
            "project_id": project_id,
            "to_chapter": to_chapter,
            "kept_chapters": kept,
            "removed_chapters": removed,
        }

    async def soft_delete(self, project_id: str, confirm: bool = False) -> dict:
        """软删除（v1.3 方案 b）

        与 delete() 区别：额外写 projects_deleted 表
        返回 {trash_path, deleted_at}
        """
        # 软删前先读元数据
        project = await self.load(project_id) or {}
        result = await self.delete(project_id, confirm=confirm)
        # 写 projects_deleted 表
        pd_repo = ProjectDeletedRepository()
        await pd_repo.add(
            project_id=project_id,
            original_name=project.get("name", project_id),
            palette=project.get("palette", ""),
            trash_path=result["trash_path"],
        )
        return result

    async def delete(self, project_id: str, confirm: bool = False) -> dict:
        """删除项目（mv 到 trash + 软标记 projects.deleted_at）"""
        if not confirm:
            raise ValueError("delete requires confirm=True")
        project_path = self.projects_root / project_id
        if not project_path.exists():
            raise FileNotFoundError(f"Project not found: {project_id}")
        self.trash_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        trash_path = self.trash_root / f"{project_id}-{timestamp}"
        await asyncio.to_thread(shutil.move, str(project_path), str(trash_path))
        # 软标记（DB）
        self._proj_repo.soft_delete(project_id)
        return {
            "project_id": project_id,
            "trash_path": str(trash_path),
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
        # DB 取消软删标记
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE projects SET deleted_at = NULL WHERE id = ?",
                (project_id,),
            )
        return {"project_id": project_id, "restored_from": str(trash_path)}

