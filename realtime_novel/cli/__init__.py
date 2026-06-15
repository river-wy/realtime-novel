"""cli — 命令行入口（argparse，零依赖）

4 个子命令（M-α 阶段 stub，M-γ 阶段实装 5 步启动链路）:
- new       新建项目（5 步引导）
- load      加载并显示项目信息
- generate  生成下一章
- rollback  回档到指定 Node

设计原则:
- 用 argparse 标准库（零依赖）
- 每个子命令独立模块（cmd_*.py）
- 不在 CLI 里塞验收逻辑（tests/ 独立）
"""
from .main import main

__all__ = ["main"]
