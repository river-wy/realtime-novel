"""v0.9.1 批量工具测试（pytest）

覆盖：
- EditArtifactBatchInput / EditArtifactBatchResult / EditArtifactItem schema
- EditArtifactBatchTool 类注册 + run_batch 行为
- AGENT_TOOLS 注册
- ListProjectsTool（P1）

10 个测试用例
"""
from __future__ import annotations

import pytest
from inspect import signature


# ============ P0 batch schema ============

def test_batch_001_schema_fields():
    """EditArtifactBatchInput / EditArtifactItem 字段完整"""
    from backend.agent.tools.schemas import (
        EditArtifactBatchInput, EditArtifactBatchResult, EditArtifactItem,
    )
    in_fields = EditArtifactBatchInput.model_fields.keys()
    assert "project_id" in in_fields
    assert "items" in in_fields
    assert "atomic" in in_fields
    out_fields = EditArtifactBatchResult.model_fields.keys()
    assert "project_id" in out_fields
    assert "total" in out_fields
    assert "success_count" in out_fields
    assert "failed_count" in out_fields
    assert "results" in out_fields
    assert "failed_indices" in out_fields
    assert "rolled_back_ids" in out_fields
    item_fields = EditArtifactItem.model_fields.keys()
    assert "target" in item_fields
    assert "operation" in item_fields
    assert "identifier" in item_fields
    assert "data" in item_fields


def test_batch_002_tool_registered():
    """edit_artifact_batch tool 已注册到全局表"""
    from backend.agent.tools.base import list_tools
    assert "edit_artifact_batch" in list_tools()


def test_batch_003_tool_class():
    """EditArtifactBatchTool 类 + name + schema 完整"""
    from backend.agent.tools.edit_artifact_tool import EditArtifactBatchTool
    from backend.agent.tools.schemas import EditArtifactBatchInput, EditArtifactBatchResult
    assert EditArtifactBatchTool.name == "edit_artifact_batch"
    assert EditArtifactBatchTool.input_schema == EditArtifactBatchInput
    assert EditArtifactBatchTool.output_schema == EditArtifactBatchResult


def test_batch_004_wtm_white_list():
    """WTM 白名单含 edit_artifact_batch"""
    from backend.agent.tools.registry import AGENT_TOOLS
    assert "edit_artifact_batch" in AGENT_TOOLS["world_tree_manager"]


def test_batch_005_steward_white_list_excludes_batch():
    """管家白名单不含 edit_artifact_batch（避免管家直接批量改基座）"""
    from backend.agent.tools.registry import AGENT_TOOLS
    assert "edit_artifact_batch" not in AGENT_TOOLS["novel_steward"]


def test_batch_006_input_validation():
    """EditArtifactBatchInput items 长度限制（1-50）"""
    from backend.agent.tools.schemas import EditArtifactBatchInput, EditArtifactItem
    from pydantic import ValidationError

    # 0 items 应该报错
    with pytest.raises(ValidationError):
        EditArtifactBatchInput(project_id="p1", items=[])

    # 51 items 应该报错
    big_items = [EditArtifactItem(target="character", operation="add", data={"name": f"n{i}"}) for i in range(51)]
    with pytest.raises(ValidationError):
        EditArtifactBatchInput(project_id="p1", items=big_items)

    # 1 item OK
    ok = EditArtifactBatchInput(
        project_id="p1",
        items=[EditArtifactItem(target="character", operation="add", data={"name": "ok"})],
    )
    assert len(ok.items) == 1
    assert ok.atomic is True  # default


def test_batch_007_target_literal_match():
    """EditArtifactItem.target 跟 EditArtifactInput.target Literal 一致"""
    from backend.agent.tools.schemas import EditArtifactItem, EditArtifactInput
    item_targets = set(EditArtifactItem.model_fields["target"].annotation.__args__)
    input_targets = set(EditArtifactInput.model_fields["target"].annotation.__args__)
    assert item_targets == input_targets, f"item={item_targets} input={input_targets}"


def test_batch_008_run_batch_method_exists():
    """EditArtifactTool.run_batch 方法存在 + 签名"""
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    assert hasattr(EditArtifactTool, "run_batch")
    sig = signature(EditArtifactTool.run_batch)
    assert "input" in sig.parameters
    assert "progress_callback" in sig.parameters


def test_batch_009_run_batch_handles_unknown_target():
    """run_batch 遇到 Literal 合法但 handler 找不到的 target：标 failed + 不抛错

    v0.9.1 修复后：所有 Literal target 都有对应 handler；
    验证 schema 校验挡在前面（构造 batch 时如果 target 不在 Literal 里直接报错）。
    """
    from backend.agent.tools.schemas import EditArtifactBatchInput, EditArtifactItem
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    from backend.agent.tools.schemas import EditArtifactBatchResult
    from pydantic import ValidationError
    import asyncio

    # v0.9.1 修复后：所有 Literal 都有 handler —— 测 schema 校验挡住 unknown target
    with pytest.raises(ValidationError):
        EditArtifactBatchInput(
            project_id="p1",
            items=[EditArtifactItem(target="not_in_literal", operation="add", data={})],
            atomic=False,
        )

    # v0.9.1 修复后：_HANDLER_MAP 跟 Literal 完全对齐
    tool = EditArtifactTool()
    assert set(EditArtifactItem.model_fields["target"].annotation.__args__) == set(tool._HANDLER_MAP.keys())


# ============ P1 list_projects ============

def test_list_projects_001_schema():
    """ListProjectsInput / ListProjectsOutput 字段"""
    from backend.agent.tools.project_tools import ListProjectsInput, ListProjectsOutput
    in_fields = ListProjectsInput.model_fields.keys()
    assert "limit" in in_fields
    assert "offset" in in_fields
    assert "include_deleted" in in_fields
    out_fields = ListProjectsOutput.model_fields.keys()
    assert "projects" in out_fields
    assert "total" in out_fields


# ============ v0.9.1 死代码修复（Literal vs handler_map 对齐） ============

def test_v091_001_literal_handler_alignment():
    """v0.9.1 修复：EditArtifactInput.target Literal == EditArtifactTool._HANDLER_MAP keys

    修复前：4 个 Literal target（project_palette/timeline/geography/beat）找不到 handler
    修复后：13 个 target 全部对齐
    """
    from backend.agent.tools.schemas import EditArtifactInput, EditArtifactItem
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool

    literal_keys = set(EditArtifactInput.model_fields["target"].annotation.__args__)
    item_keys = set(EditArtifactItem.model_fields["target"].annotation.__args__)
    tool = EditArtifactTool()
    handler_keys = set(tool._HANDLER_MAP.keys())

    assert literal_keys == handler_keys, (
        f"Literal 跟 handler_map 不一致：\n"
        f"  Literal 有 handler 没有: {literal_keys - handler_keys}\n"
        f"  handler 有 Literal 没有: {handler_keys - literal_keys}"
    )
    assert item_keys == literal_keys, "EditArtifactItem Literal 跟 EditArtifactInput 不一致"


def test_v091_002_beat_no_longer_dead_code():
    """v0.9.1 修复：_edit_beat 不再死代码（在 handler_map 里）"""
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    tool = EditArtifactTool()
    assert "beat" in tool._HANDLER_MAP
    assert tool._HANDLER_MAP["beat"] is not None
    assert callable(tool._HANDLER_MAP["beat"])


def test_v091_003_project_palette_removed():
    """v0.9.1 修复：project_palette 死 Literal 已删（无 handler）"""
    from backend.agent.tools.schemas import EditArtifactInput
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    literal = set(EditArtifactInput.model_fields["target"].annotation.__args__)
    tool = EditArtifactTool()
    handler_keys = set(tool._HANDLER_MAP.keys())
    assert "project_palette" not in literal
    assert "project_palette" not in handler_keys


def test_v091_004_handler_map_property_shared():
    """v0.9.1 修复：run() 和 run_batch() 共用 _HANDLER_MAP（不重复 inline dict）"""
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    import inspect
    run_src = inspect.getsource(EditArtifactTool.run)
    batch_src = inspect.getsource(EditArtifactTool.run_batch)
    # run() 不应有 inline handler dict
    assert '"character": self._edit_character' not in run_src, "run() 不应有 inline handler dict"
    # run_batch() 不应有 inline handler dict
    assert '"character": self._edit_character' not in batch_src, "run_batch() 不应有 inline handler dict"
    # 都应引用 self._HANDLER_MAP
    assert "self._HANDLER_MAP" in run_src
    assert "self._HANDLER_MAP" in batch_src


def test_v091_005_legacy_targets_removed():
    """v0.9.1 修复：旧 'timeline' / 'geography' 都不在 Literal / handler"""
    from backend.agent.tools.schemas import EditArtifactInput
    from backend.agent.tools.edit_artifact_tool import EditArtifactTool
    literal = set(EditArtifactInput.model_fields["target"].annotation.__args__)
    tool = EditArtifactTool()
    handler_keys = set(tool._HANDLER_MAP.keys())
    # 旧名（v0.7.1 拆分前）已彻底删除
    assert "timeline" not in literal
    assert "geography" not in literal
    assert "timeline" not in handler_keys
    assert "geography" not in handler_keys
    # 新名（v0.7.1 拆分后）保留
    assert "timeline_event" in literal
    assert "geography_location" in literal
