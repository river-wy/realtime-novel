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
)


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
        # mode='json' 让 enum 序列化为字符串 (YAML/JSON 兼容)
        return {
            "world_tree": self.world_tree.model_dump(mode="json", exclude_none=True),
            "style_charter": self.style_charter.model_dump(mode="json", exclude_none=True),
            "genre_resonance": self.genre_resonance.model_dump(mode="json", exclude_none=True),
            "main_plot": self.main_plot.model_dump(mode="json", exclude_none=True),
            "character_card": self.character_card.model_dump(mode="json", exclude_none=True),
            "sub_plot": self.sub_plot.model_dump(mode="json", exclude_none=True),
            "seed_table": self.seed_table.model_dump(mode="json", exclude_none=True),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorldTree":
        """从 dict-of-dicts 反序列化"""
        return cls(
            world_tree=WorldTreeSchema.model_validate(data["world_tree"]),
            style_charter=StyleCharterSchema.model_validate(data["style_charter"]),
            genre_resonance=GenreResonanceSchema.model_validate(data["genre_resonance"]),
            main_plot=MainPlotSchema.model_validate(data["main_plot"]),
            character_card=CharacterCardSchema.model_validate(data["character_card"]),
            sub_plot=SubPlotSchema.model_validate(data["sub_plot"]),
            seed_table=SeedTableSchema.model_validate(data["seed_table"]),
        )

    # === 树形操作 ===
    # v0.8.2 删除了 from_project_dir / to_project_dir (v0.3 落盘式序列化, v0.4.1 入库后已不适用)
    # 7 件现在走 project_repository.load_all_artifacts / save_7_artifacts

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
