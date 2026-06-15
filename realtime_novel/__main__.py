"""__main__.py — 入口

用法:
    python -m realtime_novel <subcommand> [args]
"""
from .cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
