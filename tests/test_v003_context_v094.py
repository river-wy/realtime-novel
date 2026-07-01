"""v0.9.4 context_message + summary 修复测试（pytest）

覆盖：
- Bug 1: _generate_summary 不再硬编码「管家」
- Bug 2: onboarding/controller.py 注释更新
- Q1: build_project_context_message 不再含 world_tree / style_pack
- Q2: main_plot / sub_plot 只写未完成
- Q3: characters 全量（上限 16）
- Q4: seeds 只写未了结
- Q5: 章节摘要按卷聚合（历史卷 + 当前卷）

12 个测试用例
"""
from __future__ import annotations

import re
import pytest
import inspect


# ============ Bug 1: _generate_summary ============

def test_v094_bug1_summary_no_hardcoded_steward():
    """v0.9.4 Bug 修复：_generate_summary 不再硬编码「管家」

    WTM / Writer / Validator 的 assistant 消息之前都被标「管家」是错的。
    现在统一标「AI」（跟角色无关）。
    """
    from backend.agent.runtime.session_cache import _generate_summary
    import inspect
    src = inspect.getsource(_generate_summary)
    # 不能含「管家」前缀
    assert "管家：" not in src, "_generate_summary 还硬编码「管家：」"
    # 应有「AI：」标签
    assert "AI：" in src or "AI:" in src, "_generate_summary 没标 AI 标签"


# ============ Bug 2: onboarding/controller.py 注释 ============

def test_v094_bug2_controller_doc_updated():
    """v0.9.4 Bug 修复：onboarding/controller.py 注释更新到 run_initial_baseline_react"""
    from backend.agent.onboarding import controller
    src = inspect.getsource(controller)
    # 不应再有 delegate initialize_world_tree 描述
    assert "delegate WorldTreeManager.initialize_world_tree" not in src, \
        "onboarding/controller.py 注释还提 delegate initialize_world_tree（应改）"
    assert "由 WorldTreeManager.initialize_world_tree() 处理" not in src, \
        "onboarding/controller.py 错误消息还提 initialize_world_tree（应改）"
    # 应有 run_initial_baseline_react
    assert "run_initial_baseline_react" in src, \
        "onboarding/controller.py 注释应提 run_initial_baseline_react"


# ============ Q1: build_project_context_message 不含 world_tree / style_pack ============

def test_v094_q1_no_world_tree_segment():
    """v0.9.4 Q1: context 不再含 world_tree 段（sys_prompt 已有定调）"""
    from backend.agent.prompts.agent_prompt_factory import build_project_context_message
    import inspect
    src = inspect.getsource(build_project_context_message)
    # 不能再「调」_format_world_tree_compact
    assert "parts.append(_format_world_tree_compact" not in src, \
        "build_project_context_message 不应再调 _format_world_tree_compact"
    # 不应再写 world_tree segment label
    assert '"── 1. world_tree' not in src, \
        "context 不应有 world_tree 段 label"


def test_v094_q1_no_style_pack_segment():
    """v0.9.4 Q1: context 不再含 style_pack 段（sys_prompt 已有完整笔风）"""
    from backend.agent.prompts.agent_prompt_factory import build_project_context_message
    import inspect
    src = inspect.getsource(build_project_context_message)
    # 不应再写 style_pack segment label
    assert '"── 2. style_pack' not in src, \
        "context 不应有 style_pack 段 label"
    # 不应再实际调 _get_project_style_pack_id
    assert "_get_project_style_pack_id(" not in src, \
        "context 不应再实际调 _get_project_style_pack_id"


# ============ Q2: main_plot / sub_plot 只写未完成 ============

def test_v094_q2_main_plot_filter_completed():
    """v0.9.4 Q2: main_plot 只写 status != completed"""
    from backend.agent.prompts.agent_prompt_factory import build_project_context_message
    import inspect
    src = inspect.getsource(build_project_context_message)
    # 应过滤 completed
    assert 'pending_main_plot' in src or '"completed"' in src, \
        "main_plot 应过滤 status=completed"
    # 应有 "未完成的主线节点" 标签
    assert "未完成的主线节点" in src, \
        "应有「未完成的主线节点」标签"


def test_v094_q2_sub_plot_filter_completed_abandoned():
    """v0.9.4 Q2: sub_plot 只写 status not in completed/abandoned"""
    from backend.agent.prompts.agent_prompt_factory import build_project_context_message
    import inspect
    src = inspect.getsource(build_project_context_message)
    # 应过滤 completed + abandoned
    assert '"abandoned"' in src, \
        "sub_plot 应过滤 status=abandoned"
    # 应有 "未完成的支线" 标签
    assert "未完成的支线" in src, \
        "应有「未完成的支线」标签"


# ============ Q3: characters 全量（上限 16） ============

def test_v094_q3_characters_full_count():
    """v0.9.4 Q3: characters 全量写入（上限 16）"""
    from backend.agent.prompts.agent_prompt_factory import build_project_context_message
    import inspect
    src = inspect.getsource(build_project_context_message)
    # 应有 characters[:16]
    assert "characters[:16]" in src, \
        "characters 限制 16（未来支持重要等级/活跃度多级过滤）"
    # 应有 "全量，最多 16" 标签
    assert "全量" in src and "16" in src


# ============ Q4: seeds 只写未了结 ============

def test_v094_q4_seeds_filter_harvested_abandoned():
    """v0.9.4 Q4: seeds 只写 status not in harvested/abandoned"""
    from backend.agent.prompts.agent_prompt_factory import build_project_context_message
    import inspect
    src = inspect.getsource(build_project_context_message)
    # 应过滤 harvested + abandoned
    assert '"harvested"' in src and '"abandoned"' in src, \
        "seeds 应过滤 status in (harvested, abandoned)"
    # 应有 "未了结的伏笔" 标签
    assert "未了结的伏笔" in src, \
        "应有「未了结的伏笔」标签"


# ============ Q5: 章节摘要按卷聚合 ============

def test_v094_q5_chapter_summary_by_volume():
    """v0.9.4 Q5: 章节摘要改用卷维度聚合（detailed_summary 已删）"""
    from backend.agent.prompts.agent_prompt_factory import build_project_context_message
    import inspect
    src = inspect.getsource(build_project_context_message)
    # 应调 _format_chapter_summaries_by_volume
    assert "_format_chapter_summaries_by_volume" in src, \
        "应调 _format_chapter_summaries_by_volume"
    # 不应再调 _format_chapter_summaries_short / graded
    assert "_format_chapter_summaries_short" not in src, \
        "不应再调 _format_chapter_summaries_short（已替换）"
    assert "_format_chapter_summaries_graded" not in src, \
        "不应再调 _format_chapter_summaries_graded（已替换）"


def test_v094_q5_helper_function_exists():
    """v0.9.4 Q5: _format_chapter_summaries_by_volume 函数存在"""
    from backend.agent.context._helpers import _format_chapter_summaries_by_volume
    assert callable(_format_chapter_summaries_by_volume)


def test_v094_q5_helper_function_behavior():
    """v0.9.4 Q5: _format_chapter_summaries_by_volume 按卷分组输出"""
    from backend.agent.context._helpers import _format_chapter_summaries_by_volume

    class MockVol:
        def __init__(self, id, num, title, desc):
            self.id, self.volume_num, self.title, self.description = id, num, title, desc

    class MockCh:
        def __init__(self, num, vid, title="", summary=""):
            self.chapter_num, self.volume_id, self.title, self.summary = num, vid, title, summary

    vols = [
        MockVol("v1", 1, "第一卷 山村", "少年林轩在偏远山村出生"),
        MockVol("v2", 2, "第二卷 入门", "主角进入修仙门派"),
    ]
    chs = [
        MockCh(1, "v1", summary="山村少年"),
        MockCh(2, "v1", summary="遇到师父"),
        MockCh(3, "v2", summary="入宗门"),
        MockCh(4, "v2", summary="宗门比试"),
    ]
    out = _format_chapter_summaries_by_volume(chs, vols)

    # 历史卷应该含 description
    assert "少年林轩在偏远山村出生" in out, \
        "历史卷 description 应在输出中"
    # 当前卷标记
    assert "当前卷" in out, \
        "最新章节所在卷应标「当前卷」"
    # 历史卷标记
    assert "历史卷" in out, \
        "其他卷应标「历史卷」"
    # 章节 summary 应有
    assert "山村少年" in out
    assert "入宗门" in out
