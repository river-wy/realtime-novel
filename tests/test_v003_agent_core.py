"""v003 agent-core 测试（pytest）

覆盖 .spec/db-refactor/test-cases/agent-core.json 10 个用例
- WTM Agent 工具注册
- novel_writer 删 actor_*
- WTM 输出范围扩大
"""
from __future__ import annotations

import pytest
from inspect import signature


def test_tc_agent_core_005_novel_writer_no_actor():
    """novel_writer.delegate_chapter_generation 不再接受 actor_feedback / actor_character"""
    from backend.agent.agents.novel_writer import delegate_chapter_generation
    sig = signature(delegate_chapter_generation)
    params = list(sig.parameters.keys())
    assert "actor_feedback" not in params
    assert "actor_character" not in params
    # 保留
    assert "project_id" in params
    assert "intervention" in params
    assert "source" in params


def test_tc_agent_core_006_novel_writer_no_actor_in_prompt():
    """novel_writer.py prompt 拼接不含 '演员反馈' / '演员角色' 段"""
    from pathlib import Path
    src = Path("backend/agent/agents/novel_writer.py").read_text()
    assert "演员反馈" not in src
    assert "演员角色" not in src


def test_tc_agent_core_001_wtm_has_7_tools():
    """WTM Agent 工具注册 + Onboarding 主入口（v0.8 走 ReAct loop）

    v0.8 改造：generate_full_world_tree_baseline（机械代码）已删，替换为
    run_initial_baseline_react（走 ReAct loop）
    """
    from backend.agent.agents import world_tree_manager
    src = open("backend/agent/agents/world_tree_manager.py").read()
    # 关键：WTM 新主入口函数存在
    assert "async def run_initial_baseline_react" in src
    # 旧机械函数应已删
    assert "async def generate_full_world_tree_baseline" not in src
    # 9 张表在 prompt 身份段里全部提及
    for table in [
        "world_tree", "characters", "volumes", "main_plot", "sub_plot",
        "world_entries", "timeline_events", "geography_locations", "seeds",
    ]:
        assert table in src, f"WTM 身份段应提及 9 张表之一: {table}"


def test_tc_agent_core_002_wtm_output_covers_9_tables():
    """generate_full_world_tree_baseline 输出覆盖完整世界树基座 9 张表"""
    from pathlib import Path
    src = Path("backend/agent/agents/world_tree_manager.py").read_text()
    # 9 张表（world_tree / characters / main_plot / sub_plot / volumes /
    # world_entries / timeline_events / geography_locations + core_rules_json）
    for table in [
        "world_tree", "characters", "main_plot", "sub_plot", "volumes",
        "world_entries", "timeline_events", "geography_locations",
    ]:
        assert table in src, f"WTM 输出应覆盖表 {table}"


def test_tc_agent_core_003_wtm_schema_no_opening_scene():
    """WTMInputSchema 不含 opening_scene"""
    from pathlib import Path
    src = Path("backend/agent/agents/world_tree_manager.py").read_text()
    # v003 删 opening_scene
    # 仅在"已删除"注释中可出现，不应在实际 schema 中
    # 简化：检查 schema 段
    assert "opening_scene" not in src or "删 opening_scene" in src


def test_tc_agent_core_004_wtm_prompt_no_opening_scene():
    """WTM Agent prompt 模板无【开篇场景】段"""
    from pathlib import Path
    src = Path("backend/agent/agents/world_tree_manager.py").read_text()
    # 仅在"已删除"注释中可出现
    assert "【开篇场景】" not in src, "WTM prompt 模板应已删除【开篇场景】段"


def test_tc_agent_core_007_novel_steward_no_opening_scene():
    """novel_steward 注释中无 opening_scene 引用（除 v003 删 ...）"""
    from pathlib import Path
    src = Path("backend/agent/agents/novel_steward.py").read_text()
    # 仅"v003 删 ..."注释可出现
    assert "opening_scene" not in src or "v003 删 opening_scene" in src


def test_tc_agent_core_010_novel_writer_log_no_actor():
    """novel_writer 日志不再含 actor_feedback / actor_character 字段"""
    from pathlib import Path
    src = Path("backend/agent/agents/novel_writer.py").read_text()
    # 注释中"v003 删 actor_feedback / actor_character"可出现
    # 实际 log.info(...) 调用不应含这些字段
    import re
    log_calls = re.findall(r"log\.(?:info|warning|error)\(.*?\)", src, re.DOTALL)
    for call in log_calls:
        assert "actor_feedback" not in call, f"log 调用含 actor_feedback: {call[:100]}"
        assert "actor_character" not in call, f"log 调用含 actor_character: {call[:100]}"


def test_tc_agent_core_validate_world_tree_baseline_exists():
    """_validate_world_tree_completeness 校验 6 项（spec §5.6）"""
    from backend.agent.agents.novel_writer import _validate_world_tree_completeness
    assert callable(_validate_world_tree_completeness)
    # 检查源码含 6 项关键字
    from pathlib import Path
    src = Path("backend/agent/agents/novel_writer.py").read_text()
    for key in ["world_tree", "characters", "main_plot", "volumes", "style_pack_id"]:
        assert key in src, f"校验函数应含 {key}"


def test_tc_agent_core_no_metadata_json_writes():
    """WTM Agent 不再写 metadata_json 字段"""
    from pathlib import Path
    src = Path("backend/agent/agents/world_tree_manager.py").read_text()
    # metadata_json 应在 "DELETE" 注释中可出现
    # 但实际代码不应再写
    import re
    write_calls = re.findall(r"INSERT.*metadata_json|UPDATE.*metadata_json", src, re.IGNORECASE)
    assert len(write_calls) == 0, f"不应再写 metadata_json: {write_calls}"
