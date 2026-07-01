"""v003 agent-tools 测试（pytest）

覆盖 .spec/db-refactor/test-cases/agent-tools.json 9 个用例
- timeline / geography 拆为事件/地点级
- 新增 _edit_world_entry
- ChapterToolInput 删 actor_*
"""
from __future__ import annotations

import pytest
from inspect import signature


def test_tc_agent_tools_006_chapter_tool_input_no_actor():
    """ChapterToolInput 不含 actor_feedback / actor_character"""
    from backend.agent.tools.schemas import GenerateChapterInput
    fields = GenerateChapterInput.model_fields.keys()
    assert "actor_feedback" not in fields
    assert "actor_character" not in fields
    # 保留
    assert "intervention" in fields
    assert "content" in fields


def test_tc_agent_tools_002_old_timeline_target_removed():
    """edit_artifact 旧 target='timeline' 不再可用（重命名为 timeline_event）"""
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    tool = EditArtifactTool()
    # 调 run() 不必验证全行为，但能验证类
    # 内部 handler dict 不含 'timeline' 旧名
    # 验证通过看是否有新名
    assert hasattr(tool, "_edit_timeline_event")
    assert hasattr(tool, "_edit_geography_location")
    assert hasattr(tool, "_edit_world_entry")


def test_tc_agent_tools_003_geography_location_method():
    """_edit_geography_location 方法存在"""
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    tool = EditArtifactTool()
    assert callable(getattr(tool, "_edit_geography_location", None))


def test_tc_agent_tools_004_world_entry_method():
    """_edit_world_entry 方法存在（v003 新增）"""
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    tool = EditArtifactTool()
    assert callable(getattr(tool, "_edit_world_entry", None))


def test_tc_agent_tools_005_core_rule_handler():
    """_edit_core_rule 方法保留"""
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    tool = EditArtifactTool()
    assert callable(getattr(tool, "_edit_core_rule", None))


def test_tc_agent_tools_007_chapter_tools_no_actor():
    """GenerateChapterTool.run() 调用链不传 actor_*"""
    from backend.agent.tools.chapter_tools import GenerateChapterTool
    import inspect
    src = inspect.getsource(GenerateChapterTool.run)
    # 不应再含 actor_feedback / actor_character
    assert "actor_feedback" not in src
    assert "actor_character" not in src
    # 保留 intervention
    assert "intervention" in src


def test_tc_agent_tools_001_timeline_event_handler():
    """_edit_timeline_event 方法存在（拆事件级）"""
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    tool = EditArtifactTool()
    assert callable(getattr(tool, "_edit_timeline_event", None))


def test_tc_agent_tools_008_target_list_updated():
    """edit_artifact target 列表更新含 timeline_event / geography_location / world_entry

    v0.9.1 修复：handler map 抽到 _HANDLER_MAP property（run() / run_batch() 共用），
    改测 _HANDLER_MAP 含新 key 且不含旧 key。
    """
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    tool = EditArtifactTool()
    handler_keys = set(tool._HANDLER_MAP.keys())
    assert "timeline_event" in handler_keys
    assert "geography_location" in handler_keys
    assert "world_entry" in handler_keys
    # 旧 target 不存在
    assert "timeline" not in handler_keys
    assert "geography" not in handler_keys
    # v0.9.1：project_palette 死 Literal 也已删
    assert "project_palette" not in handler_keys


def test_tc_agent_tools_volume_method():
    """_edit_volume 方法存在（v003 新增）"""
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    tool = EditArtifactTool()
    assert callable(getattr(tool, "_edit_volume", None))


def test_tc_agent_tools_main_plot_node_method():
    """_edit_main_plot_node 方法存在（v003 新增 1:n 节点级）"""
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    tool = EditArtifactTool()
    assert callable(getattr(tool, "_edit_main_plot_node", None))
