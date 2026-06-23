"""cli/main.py — CLI 入口（M-ε 启动后保留, 但引导用户用 API）

M-ε 启动 (2026-06-15) 后, CLI 入口不再被推荐使用:
- frontend/ UI (M-ε.5 实装) 是首选
- HTTP API (realtime-novel-api) 可直接调

但 CLI 入口保留 (供脚本/CI 调用):
- 默认行为: 提示用户用 API
- --legacy 参数: 调原 5 子命令 (main.py.cli-deprecated)

完整实现见 main.py.cli-deprecated (备份)
"""
from __future__ import annotations

import sys
from pathlib import Path


_LEGACY_HINT = """
⚠️  CLI 5 子命令已 deprecated (M-ε 启动后)
    完整实现在 main.py.cli-deprecated
    临时启用: realtime-novel --legacy <subcommand> [args]

💡 推荐: 用 HTTP API
    启动: realtime-novel-api  (默认 http://127.0.0.1:7777)
    UI:   M-ε.5 frontend/ (即将实装)
"""


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口
    - 无参数: 提示用户用 API
    - --legacy: 调原 5 子命令实现
    """
    if argv is None:
        argv = sys.argv[1:]

    if "--legacy" in argv:
        # 调原 5 子命令
        argv.remove("--legacy")
        # 动态 import 备份实现 (用 runpy 调 .py 文件, 走其顶部 if __name__ 逻辑)
        # 但 main.py.cli-deprecated 是 importable Python module, 用 importlib
        import importlib.util
        import importlib.machinery
        backup_path = Path(__file__).parent / "main.py.cli-deprecated"
        loader = importlib.machinery.SourceFileLoader(
            "main_cli_deprecated", str(backup_path)
        )
        spec = importlib.util.spec_from_loader("main_cli_deprecated", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod.main(argv)
    else:
        # 默认: 提示
        print(_LEGACY_HINT)
        return 0


__all__ = ["main"]
