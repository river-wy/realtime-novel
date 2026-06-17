"""v0.4 Async 包装层（不重写 v0.3 逻辑）

设计：v0.3 内部服务是同步实现，v0.4 通过 AsyncProjectManager（仅基于 ProjectManager）
保持兼容，ChapterGenerator/OnboardingFlow/InterventionParser/RollbackManager 的
v0.3 内部实现被 tools 层直接调同步方法（+ asyncio.to_thread）。

v0.4 变更：
- AsyncProjectManager: 修 workspace_root 参数适配 v0.3 ProjectManager
- 其他 Async 包装暂时是 stub，Phase 2-3 时由 tools 层按需直接调 v0.3 同步方法
"""
from __future__ import annotations

import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from realtime_novel.core.project import ProjectManager


class AsyncProjectManager:
    """v0.3 ProjectManager 异步包装 + v0.4 新增 delete（v1.3 软删方案 b）"""

    def __init__(self, workspace_root: Path | str = "data"):
        # v0.3 ProjectManager 接受 workspace_root，自动加 'projects' 子目录
        self._sync = ProjectManager(workspace_root=Path(workspace_root))
        self.projects_root = Path(workspace_root) / "projects"
        self.workspace_root = Path(workspace_root)
        self.trash_root = self.projects_root / ".trash"

    async def create(self, name: str, palette: str, initial_prompt: Optional[str] = None) -> dict:
        """v0.4 create(name, palette, prompt) - v0.4 独立实现

        不调 v0.3 ProjectManager.create()（依赖 pydantic v1 旧接口，与 v0.4 环境冲突）
        v0.4 直接用文件系统 + YAML 初始化项目骨架
        """
        import time
        import yaml
        project_path = self.projects_root / name
        if project_path.exists():
            raise FileExistsError(f"Project {name} already exists")
        project_path.mkdir(parents=True)
        (project_path / "chapters").mkdir()
        # 7_artifacts.yaml 默认内容
        artifacts = {
            "name": name,
            "palette": palette,
            "initial_prompt": initial_prompt or "",
            "created_at": time.time(),
            "world_tree": {},
            "main_plot": "",
            "style_charter": {"raw": ""},
            "seed_table": [],
            "genre_resonance": {},
            "current_pov": "",
        }
        (project_path / "7_artifacts.yaml").write_text(
            yaml.safe_dump(artifacts, allow_unicode=True)
        )
        # project.yaml
        (project_path / "project.yaml").write_text(
            yaml.safe_dump({"id": name, "name": name, "palette": palette}, allow_unicode=True)
        )
        # world_tree.json
        import json
        (project_path / "world_tree.json").write_text(json.dumps({"characters": [], "locations": []}))
        return {"id": name, "name": name, "palette": palette}

    async def load(self, project_id: str) -> Optional[dict]:
        """v0.4 独立 load（不调 v0.3）"""
        import json
        project_path = self.projects_root / project_id
        if not project_path.exists():
            return None
        # 读 7_artifacts.yaml
        import yaml
        yaml_path = project_path / "7_artifacts.yaml"
        artifacts = {}
        if yaml_path.exists():
            artifacts = yaml.safe_load(yaml_path.read_text()) or {}
        # 列章节
        chapters = []
        chapters_dir = project_path / "chapters"
        if chapters_dir.exists():
            for f in sorted(chapters_dir.glob("chapter_*.md")):
                num = int(f.stem.split("_")[1])
                chapters.append({"num": num, "title": f"第 {num} 章"})
        return {
            "id": project_id,
            "name": artifacts.get("name", project_id),
            "palette": artifacts.get("palette", ""),
            "seven_artifacts": artifacts,
            "world_tree": artifacts.get("world_tree", {}),
            "chapters": chapters,
        }

    async def list_projects(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """v0.4 独立 list（直接读文件系统）"""
        import yaml
        if not self.projects_root.exists():
            return []
        result = []
        for d in sorted(self.projects_root.iterdir()):
            if d.is_dir() and d.name != ".trash":
                # 读 metadata
                artifacts_path = d / "7_artifacts.yaml"
                palette = ""
                chapter_count = 0
                if artifacts_path.exists():
                    artifacts = yaml.safe_load(artifacts_path.read_text()) or {}
                    palette = artifacts.get("palette", "")
                chapters_dir = d / "chapters"
                if chapters_dir.exists():
                    chapter_count = len(list(chapters_dir.glob("chapter_*.md")))
                result.append({
                    "id": d.name,
                    "name": d.name,
                    "palette": palette,
                    "chapter_count": chapter_count,
                })
        return result[offset:offset + limit]

    async def update_base(
        self,
        project_id: str,
        key: str,
        new_value: str,
    ) -> dict:
        """改 7 件基座（spec §6.1 PATCH /base）

        返回 {old_value, new_value, chapters_affected}
        """
        import yaml
        project_path = self.projects_root / project_id
        if not project_path.exists():
            raise FileNotFoundError(f"Project not found: {project_id}")
        yaml_path = project_path / "7_artifacts.yaml"
        if yaml_path.exists():
            data = yaml.safe_load(yaml_path.read_text()) or {}
        else:
            data = {}
        old_value = str(data.get(key, ""))[:100]
        data[key] = new_value
        yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True))
        # 列章节
        chapters_dir = project_path / "chapters"
        affected = []
        if chapters_dir.exists():
            for f in chapters_dir.glob("chapter_*.md"):
                num = int(f.stem.split("_")[1])
                affected.append(num)
        return {
            "project_id": project_id,
            "key": key,
            "old_value_preview": old_value,
            "new_value_preview": new_value[:100],
            "chapters_affected": affected,
        }

    async def rollback(self, project_id: str, to_chapter: int, confirm: bool = False) -> dict:
        """回档到指定章节（spec §6.1 POST /rollback）

        返回 {kept_chapters, removed_chapters}
        """
        if not confirm:
            raise ValueError("rollback requires confirm=True")
        project_path = self.projects_root / project_id
        if not project_path.exists():
            raise FileNotFoundError(f"Project not found: {project_id}")
        chapters_dir = project_path / "chapters"
        kept = 0
        removed = 0
        if chapters_dir.exists():
            for f in chapters_dir.glob("chapter_*.md"):
                num = int(f.stem.split("_")[1])
                if num > to_chapter:
                    f.unlink()
                    removed += 1
                else:
                    kept += 1
        # 同步 chapter_status
        from realtime_novel.persistence import get_store
        with get_store().connection() as conn:
            conn.execute(
                "DELETE FROM chapter_status WHERE project_id = ? AND chapter_num > ?",
                (project_id, to_chapter),
            )
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
        from realtime_novel.persistence import ProjectDeletedRepository
        # 软删前先读元数据（删后文件已 mv，读不到）
        project = await self.load(project_id) or {}
        result = await self.delete(project_id, confirm=confirm)
        # 写 projects_deleted 表（用删前的元数据）
        pd_repo = ProjectDeletedRepository()
        await pd_repo.add(
            project_id=project_id,
            original_name=project.get("name", project_id),
            palette=project.get("palette", ""),
            trash_path=result["trash_path"],
        )
        return result

    async def delete(self, project_id: str, confirm: bool = False) -> dict:
        """v0.4 新增：软删除（v1.3 方案 b）"""
        if not confirm:
            raise ValueError("delete requires confirm=True")
        project_path = self.projects_root / project_id
        if not project_path.exists():
            raise FileNotFoundError(f"Project not found: {project_id}")
        self.trash_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        trash_path = self.trash_root / f"{project_id}-{timestamp}"
        await asyncio.to_thread(shutil.move, str(project_path), str(trash_path))
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
        return {"project_id": project_id, "restored_from": str(trash_path)}


# ============ 占位 stub（Phase 2-3 工具层按需直接调 v0.3 同步方法）============

class AsyncChapterGenerator:
    """v0.4 章节生成占位

    v0.4 实际实现位于 realtime_novel/agent/state_graph_stub.py (generate_chapter_via_state_graph)
    路径 1: tool 层直接调 state_graph_stub（不经过 AsyncChapterGenerator）
    路径 2: 本类提供向后兼容，v0.5+ 接入真实 v0.3 ChapterGenerator

    v0.3 ChapterGenerator 接受 WorldTree/Project 实例（不是 project_id 字符串），
    与 v0.4 的 async 上下文不兼容，所以 v0.4 暂时不包装 v0.3。
    """
    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)

    async def generate_chapter(
        self,
        project_id: str,
        intervention: str | None = None,
        actor_feedback: str | None = None,
        actor_character: str | None = None,
    ) -> dict:
        """委托给 state_graph_stub.generate_chapter_via_state_graph"""
        from realtime_novel.agent.state_graph_stub import generate_chapter_via_state_graph
        return await generate_chapter_via_state_graph(
            project_id=project_id,
            intervention=intervention,
            actor_feedback=actor_feedback,
            actor_character=actor_character,
        )


class AsyncOnboardingFlow:
    """v0.4 onboarding 简化版（5 步状态机跟踪）

    v0.3 OnboardingFlow 接受 Project 实例；v0.4 接受 project_id + step + payload
    5 步状态用 SQLite 记录（v0.4 简化版：内存 dict 记录）
    """

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)
        # 5 步状态: project_id -> {step, next_step, payload}
        self._state: dict = {}

    async def step(self, project_id: str, step: str, payload: dict) -> dict:
        """执行 onboarding 单步

        step ∈ {1a, 1b, 2, 3, 4, 5}
        简化版：只记录状态 + 返回 next_step
        """
        next_step_map = {
            "1a": "1b", "1b": "2", "2": "3", "3": "4", "4": "5", "5": None,
        }
        self._state[project_id] = {
            "current_step": step,
            "payload": payload,
        }
        return {
            "step": step,
            "next_step": next_step_map.get(step),
            "payload": payload,
        }


class AsyncInterventionParser:
    """v0.4 intervention 简化版（写文件 v0.4-interventions.yaml）

    v0.3 InterventionParser 接受 project_dir；v0.4 接受 project_id
    """
    import yaml as _yaml

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)

    async def add(
        self,
        project_id: str,
        intervention: str | None = None,
        actor_feedback: str | None = None,
        actor_character: str | None = None,
    ) -> dict:
        """写干预到项目干预文件"""
        from datetime import datetime
        project_path = self.workspace_root / "projects" / project_id
        intervention_path = project_path / "interventions.yaml"
        if intervention_path.exists():
            data = self._yaml.safe_load(intervention_path.read_text()) or {"items": []}
        else:
            data = {"items": []}
        data["items"].append({
            "timestamp": datetime.now().isoformat(),
            "intervention": intervention or "",
            "actor_feedback": actor_feedback or "",
            "actor_character": actor_character or "",
        })
        intervention_path.parent.mkdir(parents=True, exist_ok=True)
        intervention_path.write_text(self._yaml.safe_dump(data, allow_unicode=True))
        return {"project_id": project_id, "accepted": True, "total": len(data["items"])}


class AsyncRollbackManager:
    """v0.4 rollback 占位（实际由 AsyncProjectManager.rollback 实现）

    保留本类以兼容老调用代码（action_routes.py 在 P0 重构后已不直接调用本类）
    """
    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)

    async def rollback(
        self, project_id: str, to_chapter: int, confirm: bool = False
    ) -> dict:
        """委托给 AsyncProjectManager.rollback"""
        from realtime_novel.services.async_wrappers import AsyncProjectManager
        pm = AsyncProjectManager(workspace_root=self.workspace_root)
        return await pm.rollback(project_id, to_chapter, confirm=confirm)


__all__ = [
    "AsyncProjectManager", "AsyncChapterGenerator", "AsyncOnboardingFlow",
    "AsyncInterventionParser", "AsyncRollbackManager",
]
