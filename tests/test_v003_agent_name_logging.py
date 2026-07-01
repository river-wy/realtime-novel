"""v0.9.2 HTTP 路由 add_message agent_name 标记测试（pytest）

覆盖：
- action_routes.py 4 处 add_message 都传了 agent_name
- chapter_routes.py 1 处 add_message 传了 agent_name
- project_routes.py 2 处 add_message 都传了 agent_name
- 7 处 add_message 没有 agent_name=None 残留
- agent_name 标签语义对（intervention/rollback/update_base → WTM，create/delete/image → 管家，chapter → 文笔家）

8 个测试用例
"""
from __future__ import annotations

import re
import pytest
import inspect


# ============ 测试工具 ============

def _extract_add_message_blocks(source: str) -> list[str]:
    """从源码里抽出所有 add_message(...) 调用块（直到下一个 await / 顶层语句）"""
    blocks = []
    for m in re.finditer(r"await conv_repo\.add_message\(", source):
        start = m.start()
        # 找匹配的 ) —— 简单按括号计数
        depth = 0
        i = m.end() - 1  # 落在 (
        while i < len(source):
            ch = source[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(source[start:i+1])
                    break
            i += 1
    return blocks


# ============ A.1: action_routes.py 4 处 ============

def test_action_routes_001_all_add_message_have_agent_name():
    """action_routes.py 4 处 add_message 都传了 agent_name"""
    from backend.api import action_routes
    src = inspect.getsource(action_routes)
    blocks = _extract_add_message_blocks(src)
    assert len(blocks) == 4, f"期望 4 处 add_message，实际 {len(blocks)}"
    for i, block in enumerate(blocks, 1):
        assert "agent_name=" in block, f"第 {i} 处 add_message 缺 agent_name:\n{block[:200]}"


def test_action_routes_002_wtm_marked_for_base_ops():
    """action_routes.py 改基座的 3 处（intervention/rollback/update_base）都标 world_tree_manager"""
    from backend.api import action_routes
    src = inspect.getsource(action_routes)
    # 找三处带 name='intervene' / 'rollback_to_node' / 'update_base' 的块
    for tool_name in ("intervene", "rollback_to_node", "update_base"):
        # 找包含 tool_name 的 add_message 块
        blocks = _extract_add_message_blocks(src)
        matched = [b for b in blocks if f'"name": "{tool_name}"' in b]
        assert len(matched) == 1, f"{tool_name} 应有 1 个 add_message 块"
        assert 'agent_name="world_tree_manager"' in matched[0], \
            f"{tool_name} 应标 world_tree_manager"


def test_action_routes_003_image_marked_steward():
    """action_routes.py image 标 novel_steward（不是 WTM 路径）"""
    from backend.api import action_routes
    src = inspect.getsource(action_routes)
    blocks = _extract_add_message_blocks(src)
    image_blocks = [b for b in blocks if '"name": "generate_image"' in b]
    assert len(image_blocks) == 1
    assert 'agent_name="novel_steward"' in image_blocks[0], \
        "image 标 novel_steward（管家直接调）"


# ============ A.2: chapter_routes.py 1 处 ============

def test_chapter_routes_001_chapter_marked_writer():
    """chapter_routes.py 章节生成标 novel_writer"""
    from backend.api import chapter_routes
    src = inspect.getsource(chapter_routes)
    blocks = _extract_add_message_blocks(src)
    chapter_blocks = [b for b in blocks if '"name": "delegate_chapter_generation"' in b]
    assert len(chapter_blocks) == 1, f"期望 1 处 delegate_chapter_generation 块"
    assert 'agent_name="novel_writer"' in chapter_blocks[0], \
        "章节生成标 novel_writer"


# ============ A.3: project_routes.py 2 处 ============

def test_project_routes_001_create_marked_steward():
    """project_routes.py create_project 标 novel_steward"""
    from backend.api import project_routes
    src = inspect.getsource(project_routes)
    blocks = _extract_add_message_blocks(src)
    create_blocks = [b for b in blocks if '"name": "create_project"' in b]
    assert len(create_blocks) == 1
    assert 'agent_name="novel_steward"' in create_blocks[0]


def test_project_routes_002_delete_marked_steward():
    """project_routes.py delete_project 标 novel_steward"""
    from backend.api import project_routes
    src = inspect.getsource(project_routes)
    blocks = _extract_add_message_blocks(src)
    delete_blocks = [b for b in blocks if '"name": "delete_project"' in b]
    assert len(delete_blocks) == 1
    assert 'agent_name="novel_steward"' in delete_blocks[0]


# ============ A.4: 7 处全检（不变式） ============

def test_invariant_001_all_routes_have_agent_name():
    """不变式：HTTP 路由层 7 处 add_message 全部传 agent_name（防止以后又忘）"""
    from backend.api import action_routes, chapter_routes, project_routes
    total = 0
    for module in (action_routes, chapter_routes, project_routes):
        src = inspect.getsource(module)
        blocks = _extract_add_message_blocks(src)
        for b in blocks:
            total += 1
            assert "agent_name=" in b, \
                f"{module.__name__} 有 add_message 缺 agent_name:\n{b[:200]}"
    # 4 + 1 + 2 = 7
    assert total == 7, f"期望 7 处 add_message，实际 {total}"


def test_invariant_002_no_null_agent_name():
    """不变式：HTTP 路由层 7 处 add_message 没有 agent_name=None"""
    from backend.api import action_routes, chapter_routes, project_routes
    for module in (action_routes, chapter_routes, project_routes):
        src = inspect.getsource(module)
        blocks = _extract_add_message_blocks(src)
        for i, b in enumerate(blocks, 1):
            assert "agent_name=None" not in b, \
                f"{module.__name__} 第 {i} 处 add_message 传了 agent_name=None"
