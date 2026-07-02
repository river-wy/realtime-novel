"""context — 上下文/工具

公开 API re-export（保持外部 import 路径不变）:
- from backend.agent.context.builders import (
    build_messages_for_steward,
    build_messages_for_worldtree_keeper,
    build_messages_for_chapter_generator,
    build_messages_for_node,
)
- load_history_messages

实现文件:
- _helpers: 私有 helper (DB 转换 + 字段格式化)
- builders: 3 角色 messages 拼装 (steward/worldtree/chapter) + 通用 node builder
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
