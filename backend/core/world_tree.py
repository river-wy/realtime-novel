"""S2 · WorldTree 内存模型

职责:
- 内存中聚合 7 件 Schema
- to_dict / from_dict 序列化
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict

from .schemas import (
    WorldTreeSchema,
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
    genre_resonance: GenreResonanceSchema
    main_plot: MainPlotSchema
    character_card: CharacterCardSchema
    sub_plot: SubPlotSchema
    seed_table: SeedTableSchema
    style_pack_id: Optional[str] = None

    # === 序列化（to_dict / from_dict） ===

    def to_dict(self) -> dict:
        """序列化为 dict（dict-of-dicts，文件名 → dict 内容）"""
        # mode='json' 让 enum 序列化为字符串 (YAML/JSON 兼容)
        return {
            "world_tree": self.world_tree.model_dump(mode="json", exclude_none=True),
            "style_pack_id": self.style_pack_id,
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
            style_pack_id=data.get("style_pack_id"),
            genre_resonance=GenreResonanceSchema.model_validate(data["genre_resonance"]),
            main_plot=MainPlotSchema.model_validate(data["main_plot"]),
            character_card=CharacterCardSchema.model_validate(data["character_card"]),
            sub_plot=SubPlotSchema.model_validate(data["sub_plot"]),
            seed_table=SeedTableSchema.model_validate(data["seed_table"]),
        )

    # === 统计/自检 ===
    # 7 件走 project_repository.load_all_artifacts / save_7_artifacts

    def summary(self) -> Dict[str, int]:
        """返回各 Schema 的关键统计"""
        return {
            "main_plot_beats": len(self.main_plot.beats),
            "main_plot_current_beat": self.main_plot.current_beat,
            "character_card_characters": len(self.character_card.characters),
            "character_card_relationships": len(self.character_card.relationships),
            "sub_plot_threads": len(self.sub_plot.threads),
            "seed_table_seeds": len(self.seed_table.seeds),
        }
