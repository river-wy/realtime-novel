"""llm.py — 产品侧 LLM 客户端（复用 lunaris 的 lib.llm_config）

设计原则:
- 不复制 lunaris 的 LLM 调用代码（避免双份维护）
- 通过 sys.path 引用 lunaris 的 lib.llm_config
- 这里是"产品侧薄包装"，只做参数调优和路径解析

注意:
- lunaris 后端依赖 macOS SSL 绕过（需用 lunaris 自己的 venv）
- 产品代码使用 realtime_novel/.venv，需先把 lunaris 加入 sys.path
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


# === 复用 lunaris 的 LLM 客户端 ===
# 路径优先 LUNARIS_ROOT 环境变量（git 拉回家后设置）
# 兑底取本机默认 /Users/wuyu/AiTest/lunaris
LUNARIS_ROOT = Path(os.environ.get("LUNARIS_ROOT", "/Users/wuyu/AiTest/lunaris"))
LUNARIS_BACKEND = LUNARIS_ROOT / "backend"

# 把 lunaris backend 加进 sys.path（只在第一次时）
if str(LUNARIS_BACKEND) not in sys.path:
    sys.path.insert(0, str(LUNARIS_BACKEND))


def call_llm(
    prompt: str,
    *,
    system_msg: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 6144,
    temperature: float = 0.7,
    use_json_format: bool = False,
    timeout: int = 180,
) -> str:
    """产品侧 LLM 调用入口（章节生成 / 摘要提取通用）

    与 lunaris 默认的差异:
    - max_tokens: 6144（3000 字章节需要）
    - temperature: 0.7（创作需要，比 lunaris 默认 0.3 高）
    - use_json_format: 默认 False（章节是散文，不是 JSON）

    Args:
        prompt: user 消息
        system_msg: 选填，强约束 system 消息
        model: 选填，默认 lunaris config 里的
        max_tokens: 默认 6144
        temperature: 默认 0.7
        use_json_format: 默认 False（章节生成）。摘要提取时传 True。
        timeout: HTTP 超时秒数
    """
    from lib.llm_config import call_llm as _lunaris_call_llm

    return _lunaris_call_llm(
        prompt,
        system_msg=system_msg,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        use_json_format=use_json_format,
        timeout=timeout,
    )
