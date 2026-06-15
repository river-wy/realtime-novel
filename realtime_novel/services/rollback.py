"""services/rollback.py — S5 RollbackManager (落盘式硬 reset)

按 docs/design/01-world-tree.md §1.4 行为:
- 世界树是单线树, 永远只保留一条主干
- 回档 = 硬 reset: 回档点之后的所有枝叶全部删除
- Node 之前的章节永久保留 (可回看)
- 回档点之后的内容被裁掉后不可恢复 (有意的设计)

职责 (M-δ 阶段):
- 调 WorldTree.rollback_to(node_id) (内存操作)
- 把修改后的 7 件 YAML 写回磁盘 (WorldTree.to_project_dir)
- 删 chapters/ 目录下 rollback_node 之后的所有 chapter-XX.txt
- 报告删了多少节点 + 多少章节
- 强警告: 被裁掉的内容不可恢复
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from ..core.world_tree import WorldTree
from ..core.exceptions import ProjectError
from ..core.project import Project


@dataclass
class RollbackResult:
    """回档结果"""
    target_node_id: str
    deleted_branches_count: int
    deleted_chapters_count: int
    remaining_chapters_count: int
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class RollbackManager:
    """S5 · 回档 orchestrator"""

    def __init__(self, tree: WorldTree, project: Project):
        self.tree = tree
        self.project = project

    def rollback(self, node_id: str, *, confirm: bool = False) -> RollbackResult:
        """回档到指定 Node (落盘式硬 reset)

        Args:
            node_id: 回档目标 Node ID
            confirm: 必须为 True 才执行 (防误操作)

        Returns:
            RollbackResult 含删除统计 + 警告

        Raises:
            ProjectError: 未确认 或 目标 Node 不存在
        """
        if not confirm:
            raise ProjectError(
                "回档是不可逆操作！必须 confirm=True 才执行。"
            )

        # 1. 记录回档前状态
        before_branches = list(self.tree.world_tree.branches)
        target_idx = self._find_node_index(node_id)
        if target_idx is None:
            raise ProjectError(f"目标 Node 不存在: {node_id}")

        # 2. 计算要删的 Node IDs
        deleted_node_ids = [
            n.id for n in before_branches[target_idx + 1:]
        ]

        # 3. 内存 rollback (WorldTree.rollback_to)
        deleted_count = self.tree.rollback_to(node_id)

        # 4. 落盘: 7 件 YAML 写回
        self.tree.to_project_dir(self.project.project_dir)

        # 5. 删 chapters/ 目录下对应的章节文件
        deleted_chapters = self._delete_chapters_after_node(node_id)

        # 6. 报告
        remaining = len(list(self.project.project_dir.glob("chapters/chapter-*.txt")))

        warnings = []
        if deleted_chapters:
            warnings.append(
                f"⚠️  以下章节被永久删除 (不可恢复): {deleted_chapters}"
            )
        if deleted_count:
            warnings.append(
                f"⚠️  WorldTree 中 {deleted_count} 个 Node 被裁掉"
            )

        return RollbackResult(
            target_node_id=node_id,
            deleted_branches_count=deleted_count,
            deleted_chapters_count=len(deleted_chapters),
            remaining_chapters_count=remaining,
            warnings=warnings,
        )

    # === 内部方法 ===

    def _find_node_index(self, node_id: str) -> int | None:
        for i, node in enumerate(self.tree.world_tree.branches):
            if node.id == node_id:
                return i
        return None

    def _delete_chapters_after_node(self, node_id: str) -> List[str]:
        """删 node_id 对应章节之后的所有 chapter-XX.txt

        规则: 解析 node_id 提取章节号, 删除 >= 该章节号的所有文件
        例: node_id='node-chapter-21' → 删 chapter-21.txt, chapter-22.txt, ...
        """
        m = re.search(r"chapter-(\d+)", node_id)
        if not m:
            # node_id 不含章节号 (如 node-001 是预生成), 不能推断要删哪章
            return []
        cutoff = int(m.group(1))

        deleted = []
        chapters_dir = self.project.project_dir / "chapters"
        if not chapters_dir.exists():
            return []

        for ch_file in sorted(chapters_dir.glob("chapter-*.txt")):
            m2 = re.search(r"chapter-(\d+)", ch_file.name)
            if m2 and int(m2.group(1)) >= cutoff:
                ch_file.unlink()
                deleted.append(ch_file.name)
        return deleted

    def list_branches(self) -> List[Tuple[str, str]]:
        """列出所有 Node (id + title) 用于回档前确认"""
        return [
            (n.id, n.title)
            for n in self.tree.world_tree.branches
        ]
