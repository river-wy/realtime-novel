"""cli/interactive.py — 终端交互工具（input/confirm/menu）

零依赖 — 用标准 input() + 简单格式约定。
复杂交互（inquirer/questionary 之类）M-γ 不需要。
"""
from __future__ import annotations

import sys
from typing import List, Optional


def prompt(message: str, *, default: Optional[str] = None) -> str:
    """单行输入提示

    Args:
        message: 提示文本
        default: 默认值（用户直接回车时返回）
    """
    suffix = f" [{default}]" if default else ""
    raw = input(f"{message}{suffix}: ").strip()
    if not raw and default is not None:
        return default
    return raw


def confirm(message: str, *, default: bool = True) -> bool:
    """是/否确认"""
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"{message} {suffix}: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes", "是"):
            return True
        if raw in ("n", "no", "否"):
            return False
        print("  (请输入 y/n)")


def multi_select(message: str, options: List[str], *, allow_skip: bool = False) -> List[str]:
    """多选菜单

    Args:
        message: 提示
        options: 选项列表
        allow_skip: True 表示可输入空（跳过）/ q（退出）

    Returns:
        选中的选项列表（顺序与输入一致，可去重）
    """
    print(f"\n{message}")
    print(f"  (输入序号，多选用空格分隔，如 '1 3 5')")
    if allow_skip:
        print(f"  (直接回车跳过 / q 退出)")
    for i, opt in enumerate(options, 1):
        print(f"  {i:>3}. {opt}")

    while True:
        raw = input(f"\n选 → ").strip()
        if allow_skip and not raw:
            return []
        if raw.lower() == "q":
            sys.exit(0)
        if not raw:
            print("  (请至少选一项)")
            continue
        try:
            nums = [int(x) for x in raw.split()]
        except ValueError:
            print("  (请输入数字，空格分隔)")
            continue
        # 校验
        if any(n < 1 or n > len(options) for n in nums):
            print(f"  (序号应在 1-{len(options)} 范围内)")
            continue
        # 去重保序
        seen = set()
        picked = []
        for n in nums:
            if n not in seen:
                seen.add(n)
                picked.append(options[n - 1])
        return picked


def single_select(message: str, options: List[str]) -> str:
    """单选菜单"""
    print(f"\n{message}")
    for i, opt in enumerate(options, 1):
        print(f"  {i:>3}. {opt}")
    while True:
        raw = input(f"\n选 (1-{len(options)}) → ").strip()
        try:
            n = int(raw)
            if 1 <= n <= len(options):
                return options[n - 1]
        except ValueError:
            pass
        print(f"  (请输入 1-{len(options)} 的数字)")
