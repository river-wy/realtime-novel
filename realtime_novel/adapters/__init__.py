"""adapters — 外部依赖适配层

适配外部世界的接口（本工程都是 OpenAI 兼容协议 + 文档格式）：
- llm.py         LLM 客户端（完全独立，零外部依赖，2026-06-15 独立化）
- prompt.py      3 层 prompt 组装
- seed_weight.py 种子权重计算（02 §2.2 纯算法）
- io.py          YAML/JSON 读写（按 docs/design/03-schemas.md §4）

设计原则: adapters 内的模块是「产品代码」与「外部世界」之间的桥，
可以独立替换实现而不影响 core/ 与 services/。
"""
from .llm import call_llm
from .prompt import build_full_prompt, build_base_layer, build_dynamic_layer, build_recent_layer
from .seed_weight import rank_seeds, calc_weight, calc_overdue_score
from .io import read, write

__all__ = [
    "call_llm",
    "build_full_prompt",
    "build_base_layer",
    "build_dynamic_layer",
    "build_recent_layer",
    "rank_seeds",
    "calc_weight",
    "calc_overdue_score",
    "read",
    "write",
]
