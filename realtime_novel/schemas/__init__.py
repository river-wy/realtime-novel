"""7 件产物 Schema — docs/design/03-schemas.md

写入顺序（03 §3.3）:
    1. WorldTree        01-world-tree.yaml
    2. StyleCharter     02-style-charter.yaml
    3. GenreResonance   03-genre-resonance.yaml
    4. MainPlot         04-main-plot.yaml
    5. CharacterCard    06-character-card.yaml
    6. SubPlot          05-sub-plot.yaml
    7. SeedTable        07-seed-table.yaml
"""
from .world_tree import WorldTreeSchema
from .style_charter import StyleCharterSchema
from .genre_resonance import GenreResonanceSchema
from .main_plot import MainPlotSchema
from .sub_plot import SubPlotSchema
from .character_card import CharacterCardSchema
from .seed_table import SeedTableSchema

# 7 件 Schema → 写入顺序 → 文件名
SCHEMA_REGISTRY = [
    (WorldTreeSchema, "01-world-tree.yaml"),
    (StyleCharterSchema, "02-style-charter.yaml"),
    (GenreResonanceSchema, "03-genre-resonance.yaml"),
    (MainPlotSchema, "04-main-plot.yaml"),
    (CharacterCardSchema, "06-character-card.yaml"),  # 注意：人物在支线前（v0.2 命名）
    (SubPlotSchema, "05-sub-plot.yaml"),
    (SeedTableSchema, "07-seed-table.yaml"),
]

__all__ = [
    "WorldTreeSchema",
    "StyleCharterSchema",
    "GenreResonanceSchema",
    "MainPlotSchema",
    "SubPlotSchema",
    "CharacterCardSchema",
    "SeedTableSchema",
    "SCHEMA_REGISTRY",
]
