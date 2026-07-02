"""utils/seed_demo.py — 从 docs/eval-notes/code/cases/case-1-urban-romance/
装载 7 件 JSON 到 projects/demo-urban-romance/（YAML 形式）

用法:
    cd /Users/wuyu/creativeToys/realtime-novel
    source .venv/bin/activate
    python -m backend.utils.seed_demo
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

# utils/seed_demo.py → 工程根（往上 3 级）
ROOT = Path(__file__).resolve().parents[2]
SOURCE_CASE = ROOT / "docs" / "eval-notes" / "code" / "cases" / "case-1-urban-romance"
TARGET_PROJECT = ROOT / "projects" / "demo-urban-romance"

# case JSON 文件名 → projects YAML 文件名（保持相同语义）
FILE_MAPPING = [
    ("01-world-tree.json", "01-world-tree.yaml"),
    ("02-style-charter.json", "02-style-charter.yaml"),
    ("03-genre-resonance.json", "03-genre-resonance.yaml"),
    ("04-main-plot.json", "04-main-plot.yaml"),
    ("05-sub-plot.json", "05-sub-plot.yaml"),
    ("06-character-card.json", "06-character-card.yaml"),
    ("07-seed-table.json", "07-seed-table.yaml"),
]


def seed() -> None:
    TARGET_PROJECT.mkdir(parents=True, exist_ok=True)
    (TARGET_PROJECT / "chapters").mkdir(exist_ok=True)

    for src_name, tgt_name in FILE_MAPPING:
        src = SOURCE_CASE / src_name
        tgt = TARGET_PROJECT / tgt_name
        with src.open(encoding="utf-8") as f:
            data = json.load(f)
        with tgt.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        print(f"  ✓ {tgt.relative_to(ROOT)}")

    print(f"\n✅ Demo 装载完成: {TARGET_PROJECT.relative_to(ROOT)}")
    print(f"   {len(FILE_MAPPING)} 件 YAML 已落盘")


if __name__ == "__main__":
    seed()
