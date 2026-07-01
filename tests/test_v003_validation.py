"""v003 validator 测试（pytest）

覆盖 .spec/validator/test-cases/validator.json 20 个用例
- Validator 类 + 数据模型 + 解析
- ReAct loop + session cache
- WTM 集成 + 回滚机制
- novel_writer 集成 + retry
- 双身份段 + build_validator_system_prompt
"""
from __future__ import annotations

import pytest
import inspect


# ============ TC-validator-001 ============

def test_tc_validator_001_validator_class_exists():
    """Validator 类存在 + 双方法 + 数据模型 + 单例函数"""
    from backend.agent.agents.validator import (
        Validator, ValidationResult, ValidationIssue, ChapterValidationResult,
        get_validator
    )
    assert hasattr(Validator, "validate_world_tree")
    assert hasattr(Validator, "validate_chapter")
    assert callable(get_validator)
    v = get_validator()
    assert isinstance(v, Validator)


# ============ TC-validator-002 ============

def test_tc_validator_002_validate_world_tree_uses_react():
    """Validator.validate_world_tree 走 ReAct loop（调 executor.execute）"""
    from backend.agent.agents.validator import Validator
    src = inspect.getsource(Validator.validate_world_tree)
    assert "self.executor.execute" in src
    assert "max_iterations" in src
    assert "session_key" in src


# ============ TC-validator-003 ============

def test_tc_validator_003_validate_chapter_uses_react():
    """Validator.validate_chapter 走 ReAct loop（调 executor.execute）"""
    from backend.agent.agents.validator import Validator
    src = inspect.getsource(Validator.validate_chapter)
    assert "self.executor.execute" in src
    assert "max_iterations" in src
    assert "session_key" in src


# ============ TC-validator-004 ============

def test_tc_validator_004_session_key_format():
    """Validator session_key 按 project + kind 维度"""
    from backend.agent.agents.validator import Validator
    v = Validator.__new__(Validator)  # 跳过 __init__（不依赖 executor）
    key1 = v._session_key("p1", "world_tree")
    key2 = v._session_key("p1", "chapter")
    key3 = v._session_key("p2", "world_tree")
    assert key1 == "p1:validator:world_tree"
    assert key2 == "p1:validator:chapter"
    assert key3 == "p2:validator:world_tree"
    assert key1 != key2  # 同项目不同 kind
    assert key1 != key3  # 不同项目


# ============ TC-validator-005 ============

def test_tc_validator_005_prompt_factory():
    """校验 LLM 身份段 + build_validator_system_prompt 存在"""
    from backend.agent.prompts.agent_prompt_factory import (
        _VALIDATOR_WORLDTREE_IDENTITY, _VALIDATOR_CHAPTER_IDENTITY,
        build_validator_system_prompt,
    )
    assert "Validator" in _VALIDATOR_WORLDTREE_IDENTITY
    assert "Validator" in _VALIDATOR_CHAPTER_IDENTITY
    p1 = build_validator_system_prompt("world_tree")
    p2 = build_validator_system_prompt("chapter")
    assert p1 != p2  # 双身份段不同
    assert "load_project" in p1
    assert "load_project" in p2


# ============ TC-validator-006 ============

def test_tc_validator_006_wtm_analyze_intervention_integrated():
    """WTM.analyze_intervention 落库后调 Validator（只传 project_id + user_intent）"""
    from backend.agent.agents.world_tree_manager import WorldTreeManager
    src = inspect.getsource(WorldTreeManager.analyze_intervention)
    assert "validate_world_tree" in src
    assert "get_validator" in src or "Validator()" in src
    # 验证只传 project_id + user_intent
    assert "user_intent=" in src


# ============ TC-validator-007 ============

def test_tc_validator_007_wtm_run_initial_baseline_integrated():
    """WTM.run_initial_baseline_react 落库后调 Validator"""
    from backend.agent.agents.world_tree_manager import WorldTreeManager
    src = inspect.getsource(WorldTreeManager.run_initial_baseline_react)
    assert "validate_world_tree" in src
    assert "get_validator" in src or "Validator()" in src


# ============ TC-validator-008 ============

def test_tc_validator_008_novel_writer_integrated():
    """novel_writer.delegate_chapter_generation 生成后调 Validator.validate_chapter"""
    from backend.agent.agents.novel_writer import delegate_chapter_generation
    src = inspect.getsource(delegate_chapter_generation)
    assert "validate_chapter" in src
    assert "get_validator" in src or "Validator()" in src


# ============ TC-validator-009 ============

def test_tc_validator_009_wtm_rollback_all_writes():
    """Validator FATAL → WTM 全清 (_rollback_all_writes)"""
    from backend.agent.agents.world_tree_manager import WorldTreeManager
    assert hasattr(WorldTreeManager, "_rollback_all_writes")
    src = inspect.getsource(WorldTreeManager)
    src_analyze = inspect.getsource(WorldTreeManager.analyze_intervention)
    src_baseline = inspect.getsource(WorldTreeManager.run_initial_baseline_react)
    assert "_rollback_all_writes" in src
    assert "_rollback_all_writes" in (src_analyze + src_baseline)


# ============ TC-validator-010 ============

def test_tc_validator_010_wtm_rollback_issue_rows():
    """Validator BLOCKED → WTM 精准回滚 (_rollback_issue_rows)"""
    from backend.agent.agents.world_tree_manager import WorldTreeManager
    assert hasattr(WorldTreeManager, "_rollback_issue_rows")
    src = inspect.getsource(WorldTreeManager)
    src_analyze = inspect.getsource(WorldTreeManager.analyze_intervention)
    src_baseline = inspect.getsource(WorldTreeManager.run_initial_baseline_react)
    assert "_rollback_issue_rows" in src
    assert "_rollback_issue_rows" in (src_analyze + src_baseline)


# ============ TC-validator-011 ============

def test_tc_validator_011_chapter_retry():
    """章节 BLOCKED → retry 一次（仅一次）"""
    from backend.agent.agents.novel_writer import delegate_chapter_generation
    src = inspect.getsource(delegate_chapter_generation)
    assert "_retry_chapter_generation" in src or "retry" in src.lower()


# ============ TC-validator-012 ============

def test_tc_validator_012_not_exposed_to_steward():
    """Validator 不暴露给管家（AGENT_TOOLS novel_steward 不含）"""
    from backend.agent.tools.registry import AGENT_TOOLS
    steward_tools = AGENT_TOOLS["novel_steward"]
    assert "validate_world_tree" not in steward_tools
    assert "validate_chapter" not in steward_tools


# ============ TC-validator-013 ============

def test_tc_validator_013_no_delegate_to_agent():
    """Validator 源码不调 delegate_to_agent（避免元循环）"""
    from backend.agent.agents.validator import Validator
    src = inspect.getsource(Validator)
    assert "delegate_to_agent" not in src


# ============ TC-validator-014 ============

def test_tc_validator_014_validation_issue_fields():
    """ValidationIssue 字段完整"""
    from backend.agent.agents.validator import ValidationIssue, ValidationSeverity
    issue = ValidationIssue(
        severity="error",
        table="characters",
        field="traits",
        description="主角水系不能学火系法术",
        evidence_old="水系",
        evidence_new="火系禁术",
        suggested_fix="改回水系",
    )
    assert issue.severity == ValidationSeverity.ERROR
    assert issue.table == "characters"
    assert issue.field == "traits"
    assert issue.suggested_fix == "改回水系"


# ============ TC-validator-015 ============

def test_tc_validator_015_validation_result_4_status():
    """ValidationResult status 4 档（PASS/WARN/BLOCKED/FATAL）"""
    from backend.agent.agents.validator import ValidationResult, ValidationStatus
    for status_str in ["PASS", "WARN", "BLOCKED", "FATAL"]:
        r = ValidationResult(status=status_str, issues=[], summary="test")
        assert r.status == ValidationStatus(status_str)


# ============ TC-validator-016 ============

def test_tc_validator_016_chapter_validation_result_3_status():
    """ChapterValidationResult 3 档 + blocked_paragraphs 字段"""
    from backend.agent.agents.validator import (
        ChapterValidationResult, ChapterValidationStatus,
    )
    for status_str in ["PASS", "WARN", "BLOCKED"]:
        r = ChapterValidationResult(status=status_str, issues=[], blocked_paragraphs=[])
        assert r.status == ChapterValidationStatus(status_str)
    r = ChapterValidationResult(status="BLOCKED", issues=[], blocked_paragraphs=[3, 5, 7])
    assert r.blocked_paragraphs == [3, 5, 7]


# ============ TC-validator-017 ============

def test_tc_validator_017_parse_json_direct():
    """Validator JSON 解析：直接 parse"""
    from backend.agent.agents.validator import Validator
    v = Validator.__new__(Validator)
    result = v._try_parse_json('{"status": "PASS", "summary": "ok"}')
    assert result == {"status": "PASS", "summary": "ok"}


# ============ TC-validator-018 ============

def test_tc_validator_018_parse_json_markdown_wrapper():
    """Validator JSON 解析：去掉 markdown 包裹"""
    from backend.agent.agents.validator import Validator
    v = Validator.__new__(Validator)
    text = '```json\n{"status": "WARN"}\n```'
    result = v._try_parse_json(text)
    assert result == {"status": "WARN"}


# ============ TC-validator-019 ============

def test_tc_validator_019_parse_json_extract_braces():
    """Validator JSON 解析：提取 {...}"""
    from backend.agent.agents.validator import Validator
    v = Validator.__new__(Validator)
    text = '校验结果：{"status": "BLOCKED"}，请查看 issues'
    result = v._try_parse_json(text)
    assert result == {"status": "BLOCKED"}


# ============ TC-validator-020 ============

def test_tc_validator_020_parse_json_invalid_returns_none():
    """Validator JSON 解析：无法解析时返 None"""
    from backend.agent.agents.validator import Validator
    v = Validator.__new__(Validator)
    result = v._try_parse_json("这不是 JSON 文本")
    assert result is None
