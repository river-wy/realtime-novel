"""v004 volume 增强测试（pytest）

覆盖：
- VolumeRow 字段增强（status + summary）
- VolumeStatus 枚举
- _load_project_data 加 list_volumes（之前漏了 → 修）
- _format_chapter_summaries_by_volume 用 vol.status 区分 in_progress/completed
- _format_chapter_summaries_by_volume 完结卷优先用 vol.summary
- WTM.generate_volume_summary / complete_volume 入口存在
- v004 迁移 SQL 文件存在
"""
from __future__ import annotations

import os
import pytest
import inspect
from pathlib import Path


# ============ VolumeRow 字段 + VolumeStatus 枚举 ============

def test_v004_volume_row_has_status_field():
    """v004 增强：VolumeRow 加 status 字段"""
    from backend.persistence.models import VolumeRow, VolumeStatus
    fields = VolumeRow.model_fields.keys()
    assert "status" in fields, "VolumeRow 缺 status 字段"
    # 默认值
    v = VolumeRow(
        id="vol-test", project_id="proj-1", volume_num=1, title="t",
        updated_at="2026-01-01T00:00:00",
    )
    assert v.status == VolumeStatus.IN_PROGRESS


def test_v004_volume_row_has_summary_field():
    """v004 增强：VolumeRow 加 summary 字段"""
    from backend.persistence.models import VolumeRow
    fields = VolumeRow.model_fields.keys()
    assert "summary" in fields, "VolumeRow 缺 summary 字段"


def test_v004_volume_status_enum():
    """v004 增强：VolumeStatus 枚举"""
    from backend.persistence.models import VolumeStatus
    assert VolumeStatus.IN_PROGRESS.value == "in_progress"
    assert VolumeStatus.COMPLETED.value == "completed"


# ============ v004 迁移 SQL ============

def test_v004_migration_sql_exists():
    """v004 迁移脚本存在"""
    from pathlib import Path
    path = Path("backend/persistence/migrations/v004_volumes_enhance.sql")
    assert path.exists(), f"v004 迁移文件不存在: {path}"
    content = path.read_text()
    assert "ALTER TABLE volumes ADD COLUMN status" in content
    assert "ALTER TABLE volumes ADD COLUMN summary" in content


# ============ _load_project_data 加载 volumes ============

def test_v004_load_project_data_includes_volumes():
    """v004 增强：_load_project_data 必须读 volumes（之前漏了导致 _format_..._by_volume 无效）"""
    from backend.agent.context._helpers import _load_project_data
    src = inspect.getsource(_load_project_data)
    # 必须调 list_volumes
    assert "list_volumes" in src, \
        "_load_project_data 必须调 list_volumes（否则 by_volume 是无卷模式）"
    # 返回 dict 必须含 "volumes" key
    assert '"volumes"' in src or "'volumes'" in src, \
        "_load_project_data 返回 dict 必须含 'volumes' key"


# ============ _format_chapter_summaries_by_volume 用 vol.status/summary ============

def test_v004_format_uses_volume_status():
    """v004 增强：_format_chapter_summaries_by_volume 用 volume.status 区分完结/进行中"""
    from backend.agent.context._helpers import _format_chapter_summaries_by_volume
    src = inspect.getsource(_format_chapter_summaries_by_volume)
    # 必须有 in_progress 过滤
    assert '"in_progress"' in src, \
        "_format_..._by_volume 应有 in_progress 过滤"
    # 必须有 completed 区分
    assert '"completed"' in src, \
        "_format_..._by_volume 应有 completed 判断"
    # 完结卷 + summary 优先
    assert "vol_summary" in src, \
        "_format_..._by_volume 应有 vol_summary 变量"


def test_v004_format_completed_volume_uses_summary():
    """v004 增强：完结卷优先用 vol.summary（1000字总结）"""
    from backend.agent.context._helpers import _format_chapter_summaries_by_volume

    class MockVol:
        def __init__(self, id, num, title, status="in_progress", summary=None, description=None):
            self.id, self.volume_num, self.title = id, num, title
            self.status, self.summary, self.description = status, summary, description

    class MockCh:
        def __init__(self, num, vid, title="", summary=""):
            self.chapter_num, self.volume_id, self.title, self.summary = num, vid, title, summary

    vols = [
        MockVol("v1", 1, "第一卷", status="completed",
                summary="这是整卷总结：少年林轩从山村走出...", description="山村篇"),
        MockVol("v2", 2, "第二卷", status="in_progress"),
    ]
    chs = [
        MockCh(1, "v1", summary="山村少年"),
        MockCh(2, "v1", summary="遇到师父"),
        MockCh(3, "v2", summary="入宗门"),
    ]
    out = _format_chapter_summaries_by_volume(chs, vols)

    # 完结卷用 vol.summary 而非章节
    assert "整卷总结" in out, "完结卷应输出 vol.summary"
    # 当前卷标识
    assert "进行中" in out, "进行中卷应标 [进行中]"
    # 完结卷标识
    assert "已完结" in out, "完结卷应标 [已完结]"


def test_v004_format_unassigned_chapters():
    """v004 增强：未分配卷的章节归到"未分配卷的章节"段"""
    from backend.agent.context._helpers import _format_chapter_summaries_by_volume

    class MockCh:
        def __init__(self, num, vid, title="", summary=""):
            self.chapter_num, self.volume_id, self.title, self.summary = num, vid, title, summary

    class MockVol:
        def __init__(self, id, num, title, status="in_progress"):
            self.id, self.volume_num, self.title, self.status = id, num, title, status

    chs = [
        MockCh(1, None, summary="孤章1"),  # 无 volume_id
        MockCh(2, "v1", summary="正常章节"),
    ]
    vols = [MockVol("v1", 1, "第一卷", status="in_progress")]

    out = _format_chapter_summaries_by_volume(chs, vols)
    assert "未分配卷的章节" in out, "无 volume_id 的章节应归到未分配段"
    assert "孤章1" in out


def test_v004_format_all_completed_no_current_label():
    """v004 边缘场景：所有卷都已完结时，不应有「当前卷」标签

    背景：之前 fallback 路径会取最新章节所在卷为 current，
    会让一个 completed 的卷被误标为「当前卷 进行中」（误报）。
    修复：fallback 路径删除，无 in_progress 时 current_volume_id=None
    """
    from backend.agent.context._helpers import _format_chapter_summaries_by_volume

    class MockVol:
        def __init__(self, id, num, title, status="completed", summary=None):
            self.id, self.volume_num, self.title, self.status, self.summary = id, num, title, status, summary
    class MockCh:
        def __init__(self, num, vid, summary=""):
            self.chapter_num, self.volume_id, self.summary = num, vid, summary

    vols = [
        MockVol("v1", 1, "A卷", status="completed", summary="A卷总结"),
        MockVol("v2", 2, "B卷", status="completed", summary="B卷总结"),
    ]
    chs = [MockCh(1, "v1", summary="章1"), MockCh(2, "v2", summary="章2")]
    out = _format_chapter_summaries_by_volume(chs, vols)
    assert "当前卷" not in out, "全部已完结时不该有「当前卷」标签"
    assert "历史卷 1" in out and "历史卷 2" in out
    assert "A卷总结" in out and "B卷总结" in out


def test_v004_format_completed_no_chapter_duplicate():
    """v004 边缘场景：完结卷有 vol.summary 时不重复列章节 summary

    背景：vol.summary 1000 字足够表述整卷，不需再重复列章节 summary
    （避免冗余浪费 token）
    v0.9.6 拍板：只保留「已完结卷的 summary」+「当前卷的每个章节 summary」
    """
    from backend.agent.context._helpers import _format_chapter_summaries_by_volume

    class MockVol:
        def __init__(self, id, num, title, status="completed", summary=None):
            self.id, self.volume_num, self.title, self.status, self.summary = id, num, title, status, summary
    class MockCh:
        def __init__(self, num, vid, summary=""):
            self.chapter_num, self.volume_id, self.summary = num, vid, summary

    vols = [MockVol("v1", 1, "第一卷", status="completed", summary="1000字总结内容")]
    chs = [MockCh(1, "v1", summary="章1 summary")]
    out = _format_chapter_summaries_by_volume(chs, vols)
    # 有 vol.summary 时不应该重复列章节 summary
    assert "1000字总结内容" in out
    assert "章1 summary" not in out, "v0.9.6 拍板：完结卷有 vol.summary 时不列章节"


def test_v004_format_completed_fallback_no_summary():
    """v004 边缘场景：完结卷没 vol.summary 时回退列章节 summary"""
    from backend.agent.context._helpers import _format_chapter_summaries_by_volume

    class MockVol:
        def __init__(self, id, num, title, status="completed", summary=None, description=None):
            self.id, self.volume_num, self.title, self.status, self.summary, self.description = id, num, title, status, summary, description
    class MockCh:
        def __init__(self, num, vid, summary=""):
            self.chapter_num, self.volume_id, self.summary = num, vid, summary

    vols = [MockVol("v1", 1, "第一卷", status="completed", summary=None, description="卷描述")]
    chs = [MockCh(1, "v1", summary="章1 summary")]
    out = _format_chapter_summaries_by_volume(chs, vols)
    # 没 vol.summary 应回退到 description + 章节
    assert "卷描述" in out, "没 vol.summary 时应回退到 description"
    assert "章1 summary" in out, "没 vol.summary 时应列章节 summary"


# ============ WTM 新方法入口 ============

def test_v004_wtm_has_generate_volume_summary():
    """v004 增强：WTM 加 generate_volume_summary 方法"""
    from backend.agent.agents.world_tree_manager import WorldTreeManager
    assert hasattr(WorldTreeManager, "generate_volume_summary")
    assert callable(WorldTreeManager.generate_volume_summary)


def test_v004_wtm_has_complete_volume():
    """v004 增强：WTM 加 complete_volume 方法"""
    from backend.agent.agents.world_tree_manager import WorldTreeManager
    assert hasattr(WorldTreeManager, "complete_volume")
    assert callable(WorldTreeManager.complete_volume)


def test_v004_generate_volume_summary_signature():
    """v004 增强：generate_volume_summary 签名"""
    from backend.agent.agents.world_tree_manager import WorldTreeManager
    sig = inspect.signature(WorldTreeManager.generate_volume_summary)
    params = list(sig.parameters.keys())
    assert "project_id" in params
    assert "volume_id" in params
    assert "max_iterations" in params


def test_v004_complete_volume_signature():
    """v004 增强：complete_volume 签名"""
    from backend.agent.agents.world_tree_manager import WorldTreeManager
    sig = inspect.signature(WorldTreeManager.complete_volume)
    params = list(sig.parameters.keys())
    assert "project_id" in params
    assert "volume_id" in params
    assert "auto_generate_summary" in params


# ============ _VOLUME_SUMMARY_PROMPT 存在 ============

def test_v004_volume_summary_prompt_exists():
    """v004 增强：_VOLUME_SUMMARY_PROMPT prompt 常量"""
    from backend.agent.prompts import agent_prompt_factory
    assert hasattr(agent_prompt_factory, "_VOLUME_SUMMARY_PROMPT")
    src = agent_prompt_factory._VOLUME_SUMMARY_PROMPT
    # 关键要求
    assert "1000" in src or "一千" in src or "总结" in src
