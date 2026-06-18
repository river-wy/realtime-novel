"""导出 FastAPI OpenAPI spec 到文件

用法:
    .venv/bin/python scripts/export_openapi.py

输出:
    - docs/api/openapi.json         完整 OpenAPI 3.1 spec
    - docs/api/endpoints.md         端点列表（人话版）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 让 realtime_novel 可导入
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from realtime_novel.api.app import app


def export_openapi_json(output_path: Path) -> dict:
    """导出完整 OpenAPI spec 为 JSON"""
    spec = app.openapi()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return spec


def export_endpoints_md(spec: dict, output_path: Path) -> None:
    """导出端点列表为 Markdown"""
    lines = []
    lines.append("# realtime-novel API 端点清单")
    lines.append("")
    lines.append(f"- **Title**: {spec['info']['title']}")
    lines.append(f"- **Version**: {spec['info']['version']}")
    lines.append(f"- **OpenAPI Version**: {spec['openapi']}")
    lines.append(f"- **总端点数**: {sum(1 for p in spec['paths'].values() for m in p if m in ['get','post','put','patch','delete'])}")
    lines.append("")

    # 按 tag 分组
    by_tag: dict[str, list] = {}
    for path, methods in sorted(spec['paths'].items()):
        for method, op in methods.items():
            if method not in ['get','post','put','patch','delete']:
                continue
            tag = (op.get('tags') or ['未分类'])[0]
            by_tag.setdefault(tag, []).append((method.upper(), path, op))

    for tag in sorted(by_tag.keys()):
        lines.append(f"## {tag}")
        lines.append("")
        for method, path, op in by_tag[tag]:
            summary = op.get('summary', '')
            desc = op.get('description', '')
            op_id = op.get('operationId', '?')
            lines.append(f"### `{method} {path}`")
            lines.append("")
            if summary:
                lines.append(f"**摘要**: {summary}")
            if desc:
                lines.append(f"")
                lines.append(f"**说明**: {desc}")
            lines.append(f"")
            lines.append(f"**operationId**: `{op_id}`")
            # 列出 parameters
            params = op.get('parameters', [])
            if params:
                lines.append("")
                lines.append("**Parameters**:")
                for p in params:
                    name = p.get('name', '?')
                    location = p.get('in', '?')
                    required = '✓' if p.get('required') else ' '
                    schema_ref = p.get('schema', {}).get('type', p.get('schema', {}).get('$ref', '?'))
                    desc = p.get('description', '')
                    lines.append(f"- [{required}] `{name}` ({location}, {schema_ref}): {desc}")
            # 列出 responses
            responses = op.get('responses', {})
            if responses:
                lines.append("")
                lines.append("**Responses**:")
                for code, r in responses.items():
                    desc = r.get('description', '')
                    lines.append(f"- `{code}`: {desc}")
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    api_dir = ROOT / "docs" / "api"
    api_dir.mkdir(parents=True, exist_ok=True)

    print("1. 导出 openapi.json ...")
    spec = export_openapi_json(api_dir / "openapi.json")
    print(f"   ✓ 写入 {api_dir / 'openapi.json'} ({len(json.dumps(spec))} 字节)")

    print("2. 导出 endpoints.md ...")
    export_endpoints_md(spec, api_dir / "endpoints.md")
    print(f"   ✓ 写入 {api_dir / 'endpoints.md'}")

    print("\n✅ OpenAPI 导出完成")
