"""v0.9.5 generate_volume_summary 工具测试

覆盖：
- Tool 注册到全局表
- Schema 定义
- writer 能拿到这个 tool
- ToolError 返回（volume 不存在时）
- Tool 类的 description / name
"""
from __future__ import annotations

import inspect
import pytest


# ============ Tool 注册 ============

def test_v095_tool_registered_in_global():
    """v0.9.5: generate_volume_summary 注册到全局工具表"""
    from backend.agent.tools import list_tools
    tools = list_tools()
    assert "generate_volume_summary" in tools


def test_v095_tool_class_metadata():
    """v0.9.5: GenerateVolumeSummaryTool 类元信息"""
    from backend.agent.tools.volume_tools import GenerateVolumeSummaryTool
    assert GenerateVolumeSummaryTool.name == "generate_volume_summary"
    assert "1000" in GenerateVolumeSummaryTool.description or "总结" in GenerateVolumeSummaryTool.description


def test_v095_tool_inherits_base_tool():
    """v0.9.5: 必须继承 BaseTool"""
    from backend.agent.tools.volume_tools import GenerateVolumeSummaryTool
    from backend.agent.tools.base import BaseTool
    assert issubclass(GenerateVolumeSummaryTool, BaseTool)


# ============ Schema ============

def test_v095_input_schema():
    """v0.9.5: GenerateVolumeSummaryInput schema"""
    from backend.agent.tools.schemas import GenerateVolumeSummaryInput
    fields = GenerateVolumeSummaryInput.model_fields.keys()
    assert "project_id" in fields
    assert "volume_id" in fields
    assert "auto_complete_volume" in fields
    # auto_complete_volume 默认 False
    inp = GenerateVolumeSummaryInput(project_id="p1", volume_id="v1")
    assert inp.auto_complete_volume is False


def test_v095_output_schema():
    """v0.9.5: GenerateVolumeSummaryOutput schema"""
    from backend.agent.tools.schemas import GenerateVolumeSummaryOutput
    fields = GenerateVolumeSummaryOutput.model_fields.keys()
    assert "volume_id" in fields
    assert "summary" in fields
    assert "summary_len" in fields
    assert "auto_completed" in fields
    assert "status" in fields


# ============ 配给 writer ============

def test_v095_writer_has_volume_summary_tool():
    """v0.9.5: writer 拿到 generate_volume_summary 工具"""
    from backend.agent.tools.registry import get_tool_registry
    reg = get_tool_registry()
    writer_tools = reg.get_agent_tool_names("novel_writer")
    assert "generate_volume_summary" in writer_tools


def test_v095_writer_tool_count_increased():
    """v0.9.5: writer 工具数 4 → 5（+generate_volume_summary）"""
    from backend.agent.tools.registry import get_tool_registry
    reg = get_tool_registry()
    writer_tools = reg.get_agent_tool_names("novel_writer")
    # 之前：load_project, read_chapter, generate_chapter, summarize_chapter（4 个）
    # 现在：+ generate_volume_summary（5 个）
    assert len(writer_tools) == 5, f"writer 应有 5 个工具，实际 {len(writer_tools)}: {writer_tools}"


def test_v095_other_agents_unaffected():
    """v0.9.5: 其他 agent 不应拿到这个工具（只给 writer）"""
    from backend.agent.tools.registry import get_tool_registry
    reg = get_tool_registry()
    # 管家 / WTM 不应该有
    for agent in ["novel_steward", "world_tree_manager"]:
        tools = reg.get_agent_tool_names(agent)
        assert "generate_volume_summary" not in tools, \
            f"{agent} 不该有 generate_volume_summary（只给 writer）"


# ============ Tool 行为（mock WTM）============
# 不调真实 LLM（避免慢 + 不确定），用 monkeypatch 替换 WTM
# 项目 pytest.ini 不支持 @pytest.mark.asyncio，用 asyncio.run 包一层

import asyncio


def _run(coro):
    """同步调 async coroutine"""
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_v095_tool_volume_not_found_returns_tool_error(monkeypatch):
    """v0.9.5: volume 不存在时返回 ToolError (VOLUME_NOT_FOUND)"""
    from backend.agent.tools.volume_tools import GenerateVolumeSummaryTool
    from backend.agent.tools.schemas import GenerateVolumeSummaryInput
    from backend.agent.tools.base import ToolError

    async def fake_generate(*args, **kwargs):
        raise ValueError("volume 不存在: p1/v999")

    from backend.agent.agents import world_tree_manager
    monkeypatch.setattr(
        world_tree_manager.get_world_tree_manager(),
        "generate_volume_summary",
        fake_generate,
    )

    tool = GenerateVolumeSummaryTool()
    inp = GenerateVolumeSummaryInput(project_id="p1", volume_id="v999")
    result = _run(tool.run(inp))

    assert isinstance(result, ToolError)
    assert result.code == "VOLUME_NOT_FOUND"
    assert "v999" in result.message


def test_v095_tool_success_path(monkeypatch):
    """v0.9.5: 正常路径返回 GenerateVolumeSummaryOutput"""
    from backend.agent.tools.volume_tools import GenerateVolumeSummaryTool
    from backend.agent.tools.schemas import GenerateVolumeSummaryInput, GenerateVolumeSummaryOutput

    async def fake_generate(*args, **kwargs):
        return "这是 1000 字的卷总结内容。"

    from backend.agent.agents import world_tree_manager
    monkeypatch.setattr(
        world_tree_manager.get_world_tree_manager(),
        "generate_volume_summary",
        fake_generate,
    )

    tool = GenerateVolumeSummaryTool()
    inp = GenerateVolumeSummaryInput(project_id="p1", volume_id="v1", auto_complete_volume=False)
    result = _run(tool.run(inp))

    assert isinstance(result, GenerateVolumeSummaryOutput)
    assert result.volume_id == "v1"
    assert result.summary == "这是 1000 字的卷总结内容。"
    assert result.summary_len == len("这是 1000 字的卷总结内容。")  # 16
    assert result.auto_completed is False
    assert result.status == "in_progress"


def test_v095_tool_auto_complete_volume_path(monkeypatch):
    """v0.9.5: auto_complete_volume=True 调 WTM.complete_volume"""
    from backend.agent.tools.volume_tools import GenerateVolumeSummaryTool
    from backend.agent.tools.schemas import GenerateVolumeSummaryInput, GenerateVolumeSummaryOutput

    async def fake_generate(*args, **kwargs):
        return "卷总结"

    async def fake_complete(*args, **kwargs):
        return {
            "volume_id": "v1",
            "summary": "卷总结",
            "summary_len": 4,
            "status": "completed",
        }

    from backend.agent.agents import world_tree_manager
    mgr = world_tree_manager.get_world_tree_manager()
    monkeypatch.setattr(mgr, "generate_volume_summary", fake_generate)
    monkeypatch.setattr(mgr, "complete_volume", fake_complete)

    tool = GenerateVolumeSummaryTool()
    inp = GenerateVolumeSummaryInput(project_id="p1", volume_id="v1", auto_complete_volume=True)
    result = _run(tool.run(inp))

    assert isinstance(result, GenerateVolumeSummaryOutput)
    assert result.auto_completed is True
    assert result.status == "completed"
