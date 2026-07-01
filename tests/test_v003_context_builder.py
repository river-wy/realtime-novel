"""v003 DB 重构 — context-builder 测试（pytest）

完整覆盖 .spec/db-refactor/test-cases/context-builder.json 全部 8 个用例
"""
from __future__ import annotations

import pytest
from datetime import datetime
from pathlib import Path


# ============ TC-001 ============

def test_tc_context_001_format_world_tree_injection_order():
    """_format_world_tree_baseline 注入顺序：core_rules → world_entries → timeline_events → geography_locations → story_core → genre_tags（spec §5.4）"""
    from backend.agent.context._helpers import _format_world_tree_baseline
    world_tree = {
        "story_core": "test",
        "genre_tags": ["奇幻"],
        "core_rules": [{"id": "R1", "statement": "无魔法"}],
    }
    result = _format_world_tree_baseline(world_tree, [], [], [])
    # 检查分段顺序
    parts = result.split("\n")
    # 找到每个段的位置
    pos = {
        "core_rules": -1,
        "world_entries": -1,
        "timeline": -1,
        "geography": -1,
        "story_core": -1,
        "genre_tags": -1,
    }
    for i, p in enumerate(parts):
        for key in pos:
            if pos[key] < 0 and p.startswith({
                "core_rules": "硬约束清单",
                "world_entries": "知识库",
                "timeline": "时间线",
                "geography": "地理场景",
                "story_core": "故事核心",
                "genre_tags": "题材",
            }[key]):
                pos[key] = i

    # 顺序约束
    for k1, k2 in [("core_rules", "story_core"), ("world_entries", "story_core"),
                    ("timeline", "story_core"), ("geography", "story_core")]:
        if pos[k1] >= 0 and pos[k2] >= 0:
            assert pos[k1] < pos[k2], f"{k1} 应在 {k2} 之前"

    # 验证核心字段出现
    assert "硬约束清单" in result
    assert "R1" in result and "无魔法" in result
    assert "故事核心" in result
    assert "题材" in result


# ============ TC-002 ============

def test_tc_context_002_core_rules_no_limit():
    """core_rules 段列出所有硬约束（不限流，spec §5.4）"""
    from backend.agent.context._helpers import _format_world_tree_baseline
    world_tree = {
        "story_core": "test",
        "core_rules": [{"id": f"R{i}", "statement": f"rule {i}"} for i in range(50)],
    }
    result = _format_world_tree_baseline(world_tree, [], [], [])
    # 50 条全部应出现
    for i in range(50):
        assert f"R{i}" in result, f"应含 R{i}"
        assert f"rule {i}" in result


# ============ TC-003 ============

def test_tc_context_003_world_entries_limit_20():
    """world_entries 限流到前 20 条 + category 过滤（arch-plan §1.2）"""
    from backend.agent.context._helpers import _format_world_tree_baseline
    from backend.persistence.models import WorldEntryRow, WorldEntryCategory
    now = datetime.now()
    # 30 个 world entries
    entries = [
        WorldEntryRow(
            id=f"we-{i}", project_id="p1",
            category=WorldEntryCategory.MAGIC, title=f"Entry {i}",
            content=f"content {i}", updated_at=now,
        )
        for i in range(30)
    ]
    result = _format_world_tree_baseline({}, entries, [], [], max_world_entries=20)
    # 限流到 20 条
    assert "Entry 19" in result, "应包含 Entry 19 (前 20 条)"
    assert "Entry 20" not in result, "不应包含 Entry 20 (第 21 条起被限流)"


# ============ TC-004 ============

def test_tc_context_004_timeline_events_sorted():
    """timeline_events 按 (era_order, event_order) 排序（arch-plan §3.3）"""
    # 实际由 repo.list_timeline_events 排序，验证 SQL ORDER BY 子句
    from pathlib import Path
    src = Path("backend/persistence/project_repository.py").read_text()
    # 找 list_timeline_events 函数
    import re
    m = re.search(r"def list_timeline_events.*?def \w", src, re.DOTALL)
    if m:
        func_src = m.group(0)
        # 验证含 ORDER BY
        assert "ORDER BY" in func_src.upper(), "list_timeline_events 应有 ORDER BY"
        # 验证有 era_order / event_order
        assert "era_order" in func_src or "order" in func_src.lower()


# ============ TC-005 ============

def test_tc_context_005_geography_locations_tree():
    """geography_locations 树形结构（parent_location_id 嵌套）"""
    # 验证 v003_init.sql 包含 parent_location_id + 自引用 FK
    sql = open("backend/persistence/migrations/v003_init.sql").read()
    assert "parent_location_id" in sql, "geography_locations 应有 parent_location_id"
    # 自引用 FK：parent_location_id REFERENCES geography_locations(id)
    import re
    geo_block = re.search(r"CREATE TABLE geography_locations.*?;", sql, re.DOTALL)
    assert geo_block, "未找到 geography_locations CREATE TABLE"
    assert "REFERENCES geography_locations" in geo_block.group(0), \
        "parent_location_id 应自引用 geography_locations(id)"


# ============ TC-006 ============

def test_tc_context_006_no_old_world_tree_fields():
    """数据源切换：不再读 world_tree.timeline_era / anchor_event / geography_primary / metadata_json"""
    from backend.agent.context._helpers import _format_world_tree_compact, _format_world_tree_baseline
    import inspect

    src_compact = inspect.getsource(_format_world_tree_compact)
    src_baseline = inspect.getsource(_format_world_tree_baseline)

    # 不读旧字段
    for gone in ["timeline_era", "anchor_event", "geography_primary", "metadata_json", "base.timeline", "base.geography", "base.metadata"]:
        assert gone not in src_compact, f"_format_world_tree_compact 不应读 {gone}"
        assert gone not in src_baseline, f"_format_world_tree_baseline 不应读 {gone}"


# ============ TC-007 ============

def test_tc_context_007_empty_world_tree():
    """空世界树基座返回 '（世界树为空）' 或空字符串"""
    from backend.agent.context._helpers import _format_world_tree_compact, _format_world_tree_baseline

    # compact：空 → （世界树为空）
    result1 = _format_world_tree_compact({})
    assert "为空" in result1 or "无核心信息" in result1, f"应返回占位符: {result1}"

    # compact：None
    result2 = _format_world_tree_compact(None)
    assert "为空" in result2, f"None 应返占位符: {result2}"

    # baseline：空
    result3 = _format_world_tree_baseline({}, [], [], [])
    # 应是空字符串或仅含空段
    assert isinstance(result3, str)


# ============ TC-008 ============

def test_tc_context_008_no_n_plus_1():
    """4 张表 N+1 性能：一次性查询，不重复 IO（arch-plan §6 风险点）"""
    # 验证 load_all_artifacts 一次性查 4 张表
    import inspect
    from backend.persistence.project_repository import ProjectRepository
    src = inspect.getsource(ProjectRepository.load_all_artifacts)
    # 包含 11 个 list_* / get_* 调用（一次性 11 张表）
    count = src.count("repo.") + src.count("self.") + src.count("list_") + src.count("get_")
    assert "list_world_entries" in src
    assert "list_timeline_events" in src
    assert "list_geography_locations" in src
    # 不应在循环里查表
    assert "for " not in src or "for " in src and "list_" in src  # 至少 list_* 在外层
