"""S1 · ProjectManager

职责（来自 docs/roadmap/v0.3-product-skeleton.md §3 S1）:
- create(project_id, workspace_root) — 创建项目目录骨架 + 7 件空 YAML
- load(project_id, workspace_root)   — 加载已存在项目，校验 7 件 YAML 完整性
- list_projects(workspace_root)      — 列出所有项目 ID

项目目录结构:
    projects/{project_id}/
    ├── 01-world-tree.yaml
    ├── 02-style-charter.yaml
    ├── 03-genre-resonance.yaml
    ├── 04-main-plot.yaml
    ├── 05-sub-plot.yaml
    ├── 06-character-card.yaml
    ├── 07-seed-table.yaml
    └── chapters/
        ├── chapter-01.txt
        └── ...
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from .schemas import SCHEMA_REGISTRY
from .io import read


@dataclass
class Project:
    project_id: str
    workspace_root: Path
    project_dir: Path

    def file_path(self, schema_filename: str) -> Path:
        """单个 Schema 文件路径"""
        return self.project_dir / schema_filename

    def chapter_path(self, chapter_num: int) -> Path:
        """章节文本路径"""
        return self.project_dir / "chapters" / f"chapter-{chapter_num:02d}.txt"


class ProjectManager:
    """S1 · 项目目录管理器"""

    def __init__(self, workspace_root: Path | str):
        self.workspace_root = Path(workspace_root)
        self.projects_root = self.workspace_root / "projects"

    def create(self, project_id: str, *, exist_ok: bool = False) -> Project:
        """创建新项目目录骨架 + 7 件空 YAML + chapters/

        Args:
            project_id: 项目 ID（小写 + 短横线，如 "demo-urban-romance"）
            exist_ok: 已存在是否报错（M-α 简化：默认严格）

        Returns:
            Project 实例
        """
        project = Project(
            project_id=project_id,
            workspace_root=self.workspace_root,
            project_dir=self.projects_root / project_id,
        )

        if project.project_dir.exists() and not exist_ok:
            raise FileExistsError(
                f"项目已存在: {project.project_dir}（exist_ok=True 可跳过）"
            )

        project.project_dir.mkdir(parents=True, exist_ok=exist_ok)
        (project.project_dir / "chapters").mkdir(exist_ok=exist_ok)

        # 7 件空 YAML
        for schema_cls, filename in SCHEMA_REGISTRY:
            empty_doc = schema_cls()  # 用 Pydantic 默认值构造
            from .io import write
            write(project.file_path(filename), empty_doc.model_dump(exclude_none=True))

        return project

    def load(self, project_id: str, *, strict: bool = True) -> "LoadedProject":
        """加载已存在项目，校验 7 件 YAML 完整性

        Args:
            project_id: 项目 ID
            strict: 严格模式 = 7 件全部必须存在；False = 缺件警告但不报错

        Returns:
            LoadedProject 实例（含 7 件解析后的 Pydantic 对象）

        Raises:
            FileNotFoundError: 项目目录不存在
            ValueError: 严格模式下缺件
        """
        project = Project(
            project_id=project_id,
            workspace_root=self.workspace_root,
            project_dir=self.projects_root / project_id,
        )

        if not project.project_dir.exists():
            raise FileNotFoundError(
                f"项目不存在: {project.project_dir}"
            )

        loaded: dict[str, object] = {}
        missing: List[str] = []

        for schema_cls, filename in SCHEMA_REGISTRY:
            fpath = project.file_path(filename)
            if not fpath.exists():
                missing.append(filename)
                continue
            raw = read(fpath)
            loaded[filename] = schema_cls.model_validate(raw)

        if missing and strict:
            raise ValueError(
                f"项目 {project_id} 缺件: {missing}（strict=False 可忽略）"
            )

        return LoadedProject(
            project=project,
            artifacts=loaded,
            missing=missing,
        )

    def list_projects(self) -> List[str]:
        """列出所有项目 ID"""
        if not self.projects_root.exists():
            return []
        return sorted(
            p.name
            for p in self.projects_root.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )


@dataclass
class LoadedProject:
    """load() 返回值 — 含项目元信息 + 解析后的 7 件 Pydantic 对象"""
    project: Project
    artifacts: dict  # {filename: Pydantic instance}
    missing: List[str]

    def __getitem__(self, filename: str):
        return self.artifacts[filename]

    def __contains__(self, filename: str) -> bool:
        return filename in self.artifacts
