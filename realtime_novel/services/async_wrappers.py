"""v0.4.1 Async 包装层 — 全部走 DB（v0.4.1 文件→DB 迁移完成）

设计：
- v0.4 文件系统为根，v0.4.1 全部以 DB 为根
- ProjectRepository / ChapterRepository 是一等公民
- 章节正文仍保留文件（`data/{project_id}/chapters/chapter_NNN.md`），但 metadata 入 DB
- 工具层（P0/P1 重构后）调这里

v0.4.1 变更：
- 所有方法走 ProjectRepository / ChapterRepository
- 旧文件兼容：仍保留 `data/projects/{id}/chapters/` 文件夹，但 metadata 从 DB 读
"""
from __future__ import annotations

import asyncio
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from realtime_novel.persistence import (
    ProjectRepository, ChapterRepository, get_store,
    ProjectDeletedRepository,
)


class AsyncProjectManager:
    """v0.4.1 异步项目管理器（DB 优先）

    替代 v0.4 文件系统实现，所有操作走 ProjectRepository
    """

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)
        self.projects_root = Path(workspace_root) / "projects"
        self.chapters_root = self.projects_root  # 章节文件路径统一在 projects/{id}/chapters/
        self.trash_root = self.projects_root / ".trash"
        self._proj_repo = ProjectRepository()
        self._chap_repo = ChapterRepository()

    # ============ CRUD ============

    async def create(self, name: str, palette: str, initial_prompt: Optional[str] = None) -> dict:
        """创建项目（projects 表 + 项目目录）"""
        # 1. DB 落项目
        project = self._proj_repo.create(project_id=name, name=name, palette=palette)
        # 2. 创建项目目录（章节文件根）
        project_path = self.projects_root / name
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "chapters").mkdir(parents=True, exist_ok=True)
        return {
            "id": project.id,
            "name": project.name,
            "palette": project.palette,
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
        return {
            "id": project.id,
            "name": project.name,
            "palette": project.palette,
            "current_pov": project.current_pov,
            "seven_artifacts": all_artifacts,  # 兼容旧字段名
            "world_tree": all_artifacts.get("01-world-tree.yaml", {}),
            "chapters": chapters,
        }

    async def list_projects(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """列项目（DB 优先）"""
        projects = self._proj_repo.list_all(limit=limit + offset)
        result = []
        for p in projects[offset:]:
            # 章节数从 DB 读
            chapter_count = self._chap_repo.count_chapters(p.id)
            result.append({
                "id": p.id,
                "name": p.name,
                "palette": p.palette,
                "chapter_count": chapter_count,
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
        mapping = {
            "world_tree": "01-world-tree.yaml",
            "style_charter": "02-style-charter.yaml",
            "genre_resonance": "03-genre-resonance.yaml",
            "main_plot": "04-main-plot.yaml",
            "sub_plot": "05-sub-plot.yaml",
            "character_card": "06-character-card.yaml",
            "seed_table": "07-seed-table.yaml",
        }
        return all_data.get(mapping.get(key, ""), {})

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


# ============ 其他 Async 包装（走 DB 适配）============

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
        from realtime_novel.agent.state_graph_stub import generate_chapter_via_state_graph
        return await generate_chapter_via_state_graph(
            project_id=project_id,
            intervention=intervention,
            actor_feedback=actor_feedback,
            actor_character=actor_character,
        )


class AsyncOnboardingFlow:
    """v0.4.1 onboarding 状态机 — state 走 DB（onboarding_state 表）"""

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)

    async def step(self, project_id: str, step: str, payload: dict) -> dict:
        """执行 onboarding 单步（onboarding_state 表）

        v0.5: Step 4 触发 7 件基座生成（调 OnboardingFlow._generate_7_artifacts）
        """
        import json
        next_step_map = {
            "1": "2", "2": "3", "3": "4", "4": "5", "5": None,
        }
        now = datetime.now()
        with get_store().connection() as conn:
            # upsert state
            existing = conn.execute(
                "SELECT state_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            state_data = json.loads(existing["state_json"]) if existing else {}
            state_data["current_step"] = step
            state_data["payload"] = payload
            state_data["updated_at"] = now.isoformat()
            if existing:
                conn.execute(
                    "UPDATE onboarding_state SET current_step = ?, state_json = ?, updated_at = ? "
                    "WHERE project_id = ?",
                    (_step_to_num(step), json.dumps(state_data, ensure_ascii=False), now, project_id),
                )
            else:
                conn.execute(
                    "INSERT INTO onboarding_state (project_id, current_step, started_at, updated_at, state_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (project_id, _step_to_num(step), now, now, json.dumps(state_data, ensure_ascii=False)),
                )

        # v0.5: Step 4 触发 7 件基座生成（不生成章节，章节由 Step 5 / POST /chapters 触发）
        if step == "4":
            try:
                from realtime_novel.services.onboarding import OnboardingFlow, OnboardingState
                from realtime_novel.persistence import ProjectRepository

                # 拿全 step 1-3 的 state 用于生成 7 件
                with get_store().connection() as conn:
                    row = conn.execute(
                        "SELECT state_json FROM onboarding_state WHERE project_id = ?",
                        (project_id,),
                    ).fetchone()
                    if row:
                        full_state = json.loads(row["state_json"])

                # 构造 OnboardingState
                ob_state = OnboardingState(
                    project_id=project_id,
                    current_step=4,
                    genres=full_state.get("payload", {}).get("genres") or [],
                    styles=full_state.get("payload", {}).get("styles") or [],
                    tone=full_state.get("payload", {}).get("tone") or "",
                    palette=full_state.get("payload", {}).get("palette") or [],
                    # 注：v0.5 简化版只取 1 payload；v0.5.1 完整版要累计 1+2+3
                )
                # v0.5: 直接用 ProjectRepository.save_7_artifacts 替代 v0.3 复杂 _generate_7_artifacts
                # Step 4 在 v0.5 实际是手动生成 7 件（简化版）
                # TODO v0.5.1: 改调 LLM 真实生成
                repo = ProjectRepository()
                repo.save_7_artifacts(
                    project_id=project_id,
                    world_tree={"base": {"timeline": {"era": "现代"}, "geography": {"primary": "未设置"}}, "branches": [], "metadata": {}},
                    style_charter={"prose_style": {}, "tone": {"primary": ob_state.tone or "冷叙述"}, "density": {}, "taboos": [], "limits": {}, "metadata": {}},
                    genre_resonance={"accept": [], "reject": [], "anchors": [], "metadata": {}},
                    main_plot={"current_beat": 0, "beats": [], "metadata": {}},
                    sub_plot={"threads": [], "metadata": {}},
                    character_card={"characters": [], "relationships": []},
                    seed_table={"seeds": [], "metadata": {}},
                )
            except Exception as e:
                # 不让 onboarding 崩，返回错误信息
                import traceback
                print(f"Onboarding Step 4 失败: {e}\n{traceback.format_exc()}")
                return {
                    "step": step,
                    "next_step": None,  # 中断
                    "payload": payload,
                    "error": f"7件生成失败: {str(e)}",
                }
        return {
            "step": step,
            "next_step": next_step_map.get(step),
            "payload": payload,
        }


def _step_to_num(step: str) -> int:
    """step 名 → 数字 (1-5 顺序递增)"""
    mapping = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5}
    return mapping.get(step, 0)


class AsyncInterventionParser:
    """v0.4.1 intervention 简化版（DB 落 chapters.intervention 字段）"""

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
        from realtime_novel.persistence import ChapterRepository
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
        from realtime_novel.persistence import get_store
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


class AsyncRollbackManager:
    """v0.4.1 rollback 委托"""

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)

    async def rollback(
        self, project_id: str, to_chapter: int, confirm: bool = False
    ) -> dict:
        from realtime_novel.services.async_wrappers import AsyncProjectManager
        pm = AsyncProjectManager(workspace_root=self.workspace_root)
        return await pm.rollback(project_id, to_chapter, confirm=confirm)


__all__ = [
    "AsyncProjectManager", "AsyncChapterGenerator", "AsyncOnboardingFlow",
    "AsyncInterventionParser", "AsyncRollbackManager",
]
