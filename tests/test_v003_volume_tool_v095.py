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


# ============ v0.9.5 补: build_project_context_message 真实调用路径（v0.9.4 漏 import 修复守护）============

def test_v095_build_context_message_imports_by_volume():
    """v0.9.5 补：build_project_context_message 必须能调 _format_chapter_summaries_by_volume

    v0.9.4 漏 import 修复（欧尼酱 20:39 指出）
    背景：v0.9.4 加了 _format_chapter_summaries_by_volume 在 _helpers.py
         但 agent_prompt_factory.py 没 import
         之前所有测试只调 _helpers._format_chapter_summaries_by_volume（绕开 import 路径）
         真实调用 build_project_context_message 会 NameError
    """
    from backend.agent.prompts import agent_prompt_factory
    # 必须能从 agent_prompt_factory 直接 import
    from backend.agent.prompts.agent_prompt_factory import _format_chapter_summaries_by_volume
    assert callable(_format_chapter_summaries_by_volume)
    # import 后必须进 factory 模块的 namespace（不是 _helpers 里的）
    assert hasattr(agent_prompt_factory, "_format_chapter_summaries_by_volume")


def test_v095_build_context_message_real_call_path():
    """v0.9.5 补：build_project_context_message 真实调用路径（用 mock 替代 _load_project_data）

    背景：之前所有测试都只调 _format_chapter_summaries_by_volume，
    没走过 build_project_context_message 调它的路径。
    现在补一个 mock 完整 project_data 的端到端测试。
    """
    from backend.agent.prompts import agent_prompt_factory as factory

    class MockVol:
        def __init__(self, id, num, title, status="in_progress", summary=None, description=None):
            self.id, self.volume_num, self.title = id, num, title
            self.status, self.summary, self.description = status, summary, description
    class MockCh:
        def __init__(self, num, vid, title="", summary=""):
            self.chapter_num, self.volume_id, self.title, self.summary = num, vid, title, summary

    mock_data = {
        "exploration_level": "standard",
        "world_tree": {"story_core": "测试", "genre_tags": ["修真"], "core_rules": []},
        "main_plot": [], "sub_plot": [], "characters": [], "seeds": [],
        "volumes": [
            MockVol("v1", 1, "第一卷", status="completed", summary="完结卷总结"),
            MockVol("v2", 2, "第二卷", status="in_progress"),
        ],
        "chapters": [
            MockCh(1, "v1", title="出生", summary="少年出生"),
            MockCh(2, "v2", title="入宗", summary="入宗门"),
        ],
    }
    original = factory._load_project_data
    factory._load_project_data = lambda pid: mock_data
    try:
        # 必须不报错（之前会 NameError）
        ctx = factory.build_project_context_message("mock-pid", "novel_writer")
        assert "【项目上下文】" in ctx
        # 验证 v0.9.4 改的卷维度输出在
        assert "【历史卷 1：第一卷】" in ctx
        assert "已完结" in ctx
        assert "完结卷总结" in ctx
        assert "【当前卷 2：第二卷】" in ctx
        assert "进行中" in ctx
        assert "入宗门" in ctx
    finally:
        factory._load_project_data = original


# ============ v0.9.6 综合守护: 4 个自检问题修复 + sys_p/context 重复 + 卷摘要完整性 ============

def test_v096_retry_session_key_includes_chapter_num():
    """v0.9.6: retry session_key 加 chapter_num 隔离（避免多章 retry 累积）"""
    import inspect
    from backend.agent.agents import novel_writer
    src = inspect.getsource(novel_writer)
    # retry 路径应支持 chapter_num 参数
    assert "chapter_num: Optional[int] = None" in src
    # session_key 应拼接 chapter_num
    assert "chapter_suffix" in src
    assert 'f"{project_id}:novel_writer{chapter_suffix}"' in src


def test_v096_retry_validates_world_tree_completeness():
    """v0.9.6: retry 路径也调 _validate_world_tree_completeness"""
    import inspect
    from backend.agent.agents import novel_writer
    src = inspect.getsource(novel_writer._retry_chapter_generation)
    # 函数体内必须调 _validate_world_tree_completeness
    assert "_validate_world_tree_completeness(project_id)" in src, \
        "retry 路径必须验完整性（防上 retry 期间基座被并发删）"


def test_v096_cache_hit_validates_sys_prompt_hash():
    """v0.9.6: cache HIT 路径走 get(...) 带 hash 校验"""
    import inspect
    from backend.agent.runtime import executor
    src = inspect.getsource(executor)
    # 不再调 get_without_prompt_check（v0.9.6 改用 get）
    # 但 get(...) 必须传 sys_prompt
    assert "cache_mgr.get(" in src
    assert "sys_prompt=agent.system_prompt" in src, \
        "cache HIT 路径必须用 get(...) 带 sys_prompt hash 校验"


def test_v096_executor_marks_make_key_fragility():
    """v0.9.6: executor 加注释标记 make_key 解析脆弱性"""
    import inspect
    from backend.agent.runtime import executor
    src = inspect.getsource(executor)
    # 应有注释说明
    assert "v0.9.6" in src and ("make_key" in src or "key 格式变更" in src)


def test_v096_sys_prompt_no_internal_duplicate():
    """v0.9.6: _format_base_summary 内部去重（不再重复【题材】段）"""
    import inspect
    from backend.agent.prompts import agent_prompt_factory
    src = inspect.getsource(agent_prompt_factory._format_base_summary)
    # 不能再调 '、'.join(genre_tags) 单独输出【题材】段
    assert "、".join("str(a) for a in genre_tags") not in src, \
        "_format_base_summary 内部去重【题材】段（_format_world_tree_compact 已含）"


def test_v096_context_includes_complete_volume_history():
    """v0.9.6: context 包含「已完结卷的 vol.summary」+「当前卷的每个章节 summary」

    欧尼酱 21:24 拍板：
      - 完结卷：只保留 vol.summary，不列章节（避免冗余）
      - 当前卷：列所有章节 summary
    """
    from backend.agent.context._helpers import _format_chapter_summaries_by_volume

    class MockVol:
        def __init__(self, id, num, title, status="in_progress", summary=None):
            self.id, self.volume_num, self.title, self.status, self.summary = id, num, title, status, summary
    class MockCh:
        def __init__(self, num, vid, title="", summary=""):
            self.chapter_num, self.volume_id, self.title, self.summary = num, vid, title, summary

    # 场景: 2 已完结 + 1 进行中 + 7 章
    vols = [
        MockVol("v1", 1, "第一卷", status="completed", summary="卷1总结"),
        MockVol("v2", 2, "第二卷", status="completed", summary="卷2总结"),
        MockVol("v3", 3, "第三卷", status="in_progress"),
    ]
    chs = [
        MockCh(1, "v1", summary="章1"),
        MockCh(2, "v1", summary="章2"),
        MockCh(3, "v2", summary="章3"),
        MockCh(4, "v2", summary="章4"),
        MockCh(5, "v3", summary="章5"),
        MockCh(6, "v3", summary="章6"),
        MockCh(7, "v3", summary="章7"),
    ]
    out = _format_chapter_summaries_by_volume(chs, vols)

    # 关键守护 1: 所有历史卷 vol.summary 都在
    assert "卷1总结" in out
    assert "卷2总结" in out
    # 关键守护 2: 所有当前卷章节 summary 都在
    for s in ["章5", "章6", "章7"]:
        assert s in out, f"当前卷章节 {s} 缺失"
    # 关键守护 3: 完结卷章节 summary 不输出（v0.9.6 拍板：避免冗余）
    for s in ["章1", "章2", "章3", "章4"]:
        assert s not in out, f"完结卷章节 {s} 不应出现（v0.9.6 拍板）"


def test_v096_context_uses_chapter_title_when_available():
    """v0.9.6: 章节有 title 时输出 '第N章 标题: summary'"""
    from backend.agent.context._helpers import _format_chapter_summaries_by_volume

    class MockVol:
        def __init__(self, id, num, title, status="in_progress"):
            self.id, self.volume_num, self.title, self.status = id, num, title, status
    class MockCh:
        def __init__(self, num, vid, title="", summary=""):
            self.chapter_num, self.volume_id, self.title, self.summary = num, vid, title, summary

    vols = [MockVol("v1", 1, "第一卷", status="in_progress")]
    chs = [MockCh(1, "v1", title="出生", summary="少年出生")]
    out = _format_chapter_summaries_by_volume(chs, vols)
    assert "第1章 出生: 少年出生" in out, "章节有 title 时应输出 '第N章 标题: summary'"
