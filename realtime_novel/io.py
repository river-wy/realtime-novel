"""io.py — YAML/JSON 读写 + 路径解析

约定（来自 docs/design/03-schemas.md §4）:
- 人类编辑: YAML
- 持久化/程序读写: JSON
- 默认两种都支持（按文件后缀判断）
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def read(path: Path) -> Any:
    """根据后缀读 YAML/JSON"""
    path = Path(path)
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    elif path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"不支持的格式: {path.suffix}（仅 .yaml/.yml/.json）")


def write(path: Path, data: Any) -> None:
    """根据后缀写 YAML/JSON"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix in (".yaml", ".yml"):
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    elif path.suffix == ".json":
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        raise ValueError(f"不支持的格式: {path.suffix}")
