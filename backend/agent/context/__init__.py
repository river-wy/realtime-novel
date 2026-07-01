"""context — 上下文/工具（v0.6.1 重塑，P4 拆 context_builder 745 行）

公开 API re-export（保持外部 import 路径不变）:
- from backend.agent.context.context_builder import (
    build_messages_for_steward,
    build_messages_for_worldtree_keeper,
    build_messages_for_chapter_generator,
    build_messages_for_node,
    load_history_messages,
)

v003 变更：
- 删 onboarding_builders.py（孤儿代码：build_messages_for_onboarding_step3/4 已是空 stub，
  无外部调用方）。v0.7 旧 5 步工具已整体删除，这 2 个函数随之移除。

实现文件 (P4 拆分):
- _helpers: 私有 helper (DB 转换 + 字段格式化)
- builders: 3 角色 messages 拼装 (steward/worldtree/chapter) + 通用 node builder
- context_builder: 兼容 shim (P4 阶段保留, 标记 deprecated, 后续删)
"""
from __future__ import annotations

from backend.agent.context.builders import (
    build_messages_for_steward,
    build_messages_for_worldtree_keeper,
    build_messages_for_chapter_generator,
    build_messages_for_node,
)
from backend.agent.context._helpers import load_history_messages

__all__ = [
    "build_messages_for_steward",
    "build_messages_for_worldtree_keeper",
    "build_messages_for_chapter_generator",
    "build_messages_for_node",
    "load_history_messages",
]
