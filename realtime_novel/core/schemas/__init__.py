"""7 件产物 Schema + 章节摘要 Schema

v0.8.2: 删除了 SCHEMA_REGISTRY (v0.3 文件存储时代用, v0.4.1 入库后已不适用)
7 件现在走 project_repository.save_7_artifacts / load_all_artifacts
"""
from .world_tree import WorldTreeSchema
from .style_charter import StyleCharterSchema
from .genre_resonance import GenreResonanceSchema
from .main_plot import MainPlotSchema
from .sub_plot import SubPlotSchema
from .character_card import CharacterCardSchema
from .seed_table import SeedTableSchema
from .chapter import ChapterSummarySchema

__all__ = [
    "WorldTreeSchema",
    "StyleCharterSchema",
    "GenreResonanceSchema",
    "MainPlotSchema",
    "SubPlotSchema",
    "CharacterCardSchema",
    "SeedTableSchema",
    "ChapterSummarySchema",  # 不是 7 件之一，但产品需要
]
