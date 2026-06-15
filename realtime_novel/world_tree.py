"""S2 · WorldTree 内存模型

职责（来自 docs/roadmap/v0.3-product-skeleton.md §3 S2）:
- 内存中聚合 7 件 Schema
- to_dict / from_dict 序列化
- 树形操作（add_node / rollback_to）

关键设计（来自 docs/design/01-world-tree.md §1.4）:
- 单线树 —— 永远只保留一条主干
- 回档硬 reset —— 从回档点起，原先生成的所有枝叶全部删除
- Node 保留 —— 回档点之前的 Node 仍可回看
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict

from .schemas import (
    WorldTreeSchema,
    StyleCharterSchema,
    GenreResonanceSchema,
    MainPlotSchema,
    SubPlotSchema,
    CharacterCardSchema,
    SeedTableSchema,
    SCHEMA_REGISTRY,
)
from .io import read, write


@dataclass
class WorldTree:
    """内存中聚合 7 件 Schema

    7 件为可选项（缺件时为 None），允许部分加载
    """
    world_tree: WorldTreeSchema
    style_charter: StyleCharterSchema
    genre_resonance: GenreResonanceSchema
    main_plot: MainPlotSchema
    character_card: CharacterCardSchema
    sub_plot: SubPlotSchema
    seed_table: SeedTableSchema

    # === 序列化（to_dict / from_dict） ===

    def to_dict(self) -> dict:
        """序列化为 dict（dict-of-dicts，文件名 → dict 内容）"""
        return {
            "01-world-tree.yaml": self.world_tree.model_dump(exclude_none=True),
            "02-style-charter.yaml": self.style_charter.model_dump(exclude_none=True),
            "03-genre-resonance.yaml": self.genre_resonance.model_dump(exclude_none=True),
            "04-main-plot.yaml": self.main_plot.model_dump(exclude_none=True),
            "06-character-card.yaml": self.character_card.model_dump(exclude_none=True),
            "05-sub-plot.yaml": self.sub_plot.model_dump(exclude_none=True),
            "07-seed-table.yaml": self.seed_table.model_dump(exclude_none=True),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorldTree":
        """从 dict-of-dicts 反序列化"""
        return cls(
            world_tree=WorldTreeSchema.model_validate(data["01-world-tree.yaml"]),
            style_charter=StyleCharterSchema.model_validate(data["02-style-charter.yaml"]),
            genre_resonance=GenreResonanceSchema.model_validate(data["03-genre-resonance.yaml"]),
            main_plot=MainPlotSchema.model_validate(data["04-main-plot.yaml"]),
            character_card=CharacterCardSchema.model_validate(data["06-character-card.yaml"]),
            sub_plot=SubPlotSchema.model_validate(data["05-sub-plot.yaml"]),
            seed_table=SeedTableSchema.model_validate(data["07-seed-table.yaml"]),
        )

    @classmethod
    def from_project_dir(cls, project_dir: Path) -> "WorldTree":
        """从项目目录读 7 件 YAML/YAML 文件并构建 WorldTree"""
        project_dir = Path(project_dir)
        data = {}
        for _, filename in SCHEMA_REGISTRY:
            data[filename] = read(project_dir / filename)
        return cls.from_dict(data)

    def to_project_dir(self, project_dir: Path) -> None:
        """落盘 7 件到项目目录"""
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in self.to_dict().items():
            write(project_dir / filename, content)

    # === 树形操作 ===

    def add_node(self, node) -> None:
        """添加节点到 WorldTree.branches（支持 dict 或 TreeNode）"""
        from .schemas.world_tree import TreeNode
        if isinstance(node, dict):
            node = TreeNode.model_validate(node)
        self.world_tree.branches.append(node)

    def list_nodes(self) -> List[dict]:
        """列出所有节点"""
        return list(self.world_tree.branches)

    def find_node(self, node_id: str) -> Optional[dict]:
        """按 ID 找节点"""
        for node in self.world_tree.branches:
            if node.id == node_id:
                return node
        return None

    def rollback_to(self, node_id: str) -> int:
        """硬 reset 到指定 Node

        规则（来自 01 §1.4）:
        - 找到目标 Node
        - 目标之后的节点全部删除
        - 目标之前的节点保留

        Args:
            node_id: 回档目标 Node ID

        Returns:
            删除的节点数

        Raises:
            ValueError: 目标 Node 不存在
        """
        target_idx = None
        for i, node in enumerate(self.world_tree.branches):
            if node.id == node_id:
                target_idx = i
                break

        if target_idx is None:
            raise ValueError(f"目标 Node 不存在: {node_id}")

        # 硬 reset: 保留 [0..target_idx]，删除 (target_idx, end]
        kept = self.world_tree.branches[: target_idx + 1]
        deleted_count = len(self.world_tree.branches) - len(kept)
        self.world_tree.branches = kept

        return deleted_count

    # === 统计/自检 ===

    def summary(self) -> Dict[str, int]:
        """返回各 Schema 的关键统计"""
        return {
            "world_tree_branches": len(self.world_tree.branches),
            "main_plot_beats": len(self.main_plot.beats),
            "main_plot_current_beat": self.main_plot.current_beat,
            "character_card_characters": len(self.character_card.characters),
            "character_card_relationships": len(self.character_card.relationships),
            "sub_plot_threads": len(self.sub_plot.threads),
            "seed_table_seeds": len(self.seed_table.seeds),
        }
