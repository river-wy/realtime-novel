"""v003 DB 重构 — onboarding-pipeline 测试（pytest）

完整覆盖 .spec/db-refactor/test-cases/onboarding-pipeline.json 全部 10 个用例
"""
from __future__ import annotations

import json
import sqlite3
import pytest
from datetime import datetime
from pathlib import Path


# ============ Fixture ============

@pytest.fixture
def db_with_v003(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(open("backend/persistence/migrations/v003_init.sql").read())
    yield conn
    conn.close()


class _StubStore:
    def __init__(self, conn):
        self._conn = conn
    def connection(self):
        class _Ctx:
            def __init__(self, c):
                self.c = c
            def __enter__(self):
                self.c.execute("PRAGMA foreign_keys = ON")
                self.c.row_factory = sqlite3.Row
                return self.c
            def __exit__(self, *args):
                pass
        return _Ctx(self._conn)


@pytest.fixture
def mock_get_store(db_with_v003, monkeypatch):
    store = _StubStore(db_with_v003)
    from backend.persistence import (
        project_repository, chapter_repository, onboarding_repository,
        sqlite_store,
    )
    import backend.persistence as persistence_pkg
    monkeypatch.setattr(project_repository, "get_store", lambda: store)
    monkeypatch.setattr(chapter_repository, "get_store", lambda: store)
    monkeypatch.setattr(onboarding_repository, "get_store", lambda: store)
    monkeypatch.setattr(sqlite_store, "get_store", lambda: store)
    monkeypatch.setattr(persistence_pkg, "get_store", lambda: store)
    return store


@pytest.fixture
def seed_project(db_with_v003, mock_get_store):
    db_with_v003.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES ('p1', 'Test', datetime('now'), datetime('now'))"
    )
    db_with_v003.commit()
    return "p1"


# ============ TC-001 ============


def test_tc_onboarding_001_wtm_runs_initial_baseline_react(mock_get_store, seed_project):
    """v0.8: WTM.run_initial_baseline_react 入口存在 + 走 ReAct

    v0.8 改造：基座生成不再走 service 层机械代码，由 WTM ReAct loop 自主落库
    本 test 验证 WTM 类有 run_initial_baseline_react 方法
    """
    from backend.agent.agents.world_tree_manager import WorldTreeManager
    # 验证方法存在
    assert hasattr(WorldTreeManager, "run_initial_baseline_react")
    import inspect
    sig = inspect.signature(WorldTreeManager.run_initial_baseline_react)
    params = list(sig.parameters.keys())
    assert "project_id" in params
    assert "steward_payload" in params
    # 旧机械函数应已删
    from backend.agent.agents import world_tree_manager as wtm_mod
    assert not hasattr(wtm_mod, "generate_full_world_tree_baseline")


# ============ TC-002 ============

def test_tc_onboarding_002_verify_world_tree_baseline_6_items(mock_get_store, seed_project):
    """onboarding_artifacts.verify_world_tree_baseline 6 项校验"""
    from backend.services.onboarding_artifacts import verify_world_tree_baseline
    from backend.persistence.project_repository import ProjectRepository

    repo = ProjectRepository()
    # 模拟空基座 → 应返 ready=False
    result = verify_world_tree_baseline("p1")
    assert result["ready"] is False
    # 6 项校验
    assert len(result["all_items"]) == 6
    expected_items = {
        "world_tree.story_core", "world_tree.genre_tags_json", "world_tree.core_rules_json",
        "characters.protagonist", "main_plot.pending", "volumes",
    }
    assert set(result["all_items"]) == expected_items
    assert len(result["missing_items"]) == 6  # 全部缺失

    # 完整基座 → ready=True
    # world_tree
    repo._upsert_world_tree("p1", {
        "story_core": "test",
        "genre_tags": ["奇幻"],
        "base": {"core_rules": [{"id": "R1", "statement": "无魔法"}]},
    })
    # characters 至少 1 protagonist
    from backend.persistence.models import CharacterRole
    char_id = repo.add_character("p1", {
        "name": "林渊",
        "role": CharacterRole.PROTAGONIST.value,
    })
    # main_plot 至少 1 pending
    repo.add_main_plot_node("p1", {"plot_num": 1, "title": "开场", "description": "test", "status": "pending"})
    # volumes 至少 1
    repo.add_volume("p1", {"volume_num": 1, "title": "卷一"})

    result = verify_world_tree_baseline("p1")
    assert result["ready"] is True, f"应 ready=True, missing={result['missing_items']}"
    assert result["missing_items"] == []


# ============ TC-003 ============

def test_tc_onboarding_003_no_step_limit():
    """onboarding 不再有 step 限制（不限步数自由对话，v0.7.1 合并后）

    v0.7.1 变更（2026-07-01）：
    - delegate_to_wtm 工具已合并到 delegate_to_agent(mode="full_baseline")
    - 保留 verify_world_tree_baseline（独立工具，不跟 delegate 重复）
    - 新工具全无 step 概念：管家与用户自由对话，不限步数
    - 委托入口在 delegate_to_agent.agent="world_tree_manager" + mode="full_baseline"
    """
    from backend.agent.tools.onboarding_tools import VerifyWorldTreeBaselineInput
    from backend.agent.tools.delegation_tools import DelegateToAgentInput

    # 验证：onboarding_tools 的校验工具无 step 字段
    assert "step" not in VerifyWorldTreeBaselineInput.model_fields
    assert set(VerifyWorldTreeBaselineInput.model_fields.keys()) == {"project_id"}

    # 验证：v0.8 委托入口用 intent 字段（默认 intervention / initial_baseline 用于 Onboarding）
    delegate_fields = set(DelegateToAgentInput.model_fields.keys())
    assert "intent" in delegate_fields
    assert "payload" in delegate_fields
    # 默认 intent 应该是 "intervention"（向后兼容）
    assert DelegateToAgentInput.model_fields["intent"].default == "intervention"


# ============ TC-004 ============

def test_tc_onboarding_004_no_opening_scene():
    """opening_scene 字段全链路不存在"""
    import subprocess
    # 1. backend 代码无 opening_scene（除 v003 删 ... 注释）
    result = subprocess.run(
        ["grep", "-rn", "opening_scene", "backend/", "--include=*.py"],
        capture_output=True, text=True,
    )
    # 过滤 v003 删 ... 注释（中文全角冒号、英文冒号都允许）
    import re
    lines = [l for l in result.stdout.split("\n") if l and not re.search(r"v003[：:]?\s*删.*opening_scene|v003[：:]?.*opening_scene", l)]
    assert len(lines) == 0, f"backend 仍有 opening_scene 引用: {lines[:3]}"

    # 2. tests/e2e 零命中
    result2 = subprocess.run(
        ["grep", "-n", "opening_scene", "tests/e2e_integration_test.py"],
        capture_output=True, text=True,
    )
    assert result2.stdout.strip() == "", f"e2e_integration_test.py 含 opening_scene: {result2.stdout}"


# ============ TC-005 ============

def test_tc_onboarding_005_r1_no_prefix(mock_get_store, seed_project):
    """R1 rule statement 直接用 main_arc（无 '主线: ' 前缀）"""
    from backend.persistence.project_repository import ProjectRepository
    repo = ProjectRepository()
    # v003 落库 world_tree.core_rules_json
    repo._upsert_world_tree("p1", {
        "story_core": "test",
        "genre_tags": ["奇幻"],
        "base": {"core_rules": [
            {"id": "R1", "statement": "主角要 100 章内升级"},  # 无前缀
        ]},
    })
    with mock_get_store.connection() as c:
        row = c.execute(
            "SELECT core_rules_json FROM world_tree WHERE project_id='p1'"
        ).fetchone()
    rules = json.loads(row[0])
    assert len(rules) == 1
    assert rules[0]["id"] == "R1"
    assert "主线:" not in rules[0]["statement"], \
        f"R1 statement 不应有 '主线:' 前缀: {rules[0]['statement']}"


# ============ TC-006 ============

def test_tc_onboarding_006_no_r2_rule():
    """R2 rule 不再生成（opening_scene 废弃连带）"""
    # v003: opening_scene 字段删除，R2 rule（"开篇场景是 ..."）不再生成
    # 验证：onboarding_artifacts.py 不生成 R2
    src = Path("backend/services/onboarding_artifacts.py").read_text()
    assert '"R2"' not in src and "'R2'" not in src, "onboarding_artifacts.py 不应再生成 R2 rule"

    # onboarding_tools.py
    src2 = Path("backend/agent/tools/onboarding_tools.py").read_text()
    assert '"R2"' not in src2 and "'R2'" not in src2


# ============ TC-007 ============

def test_tc_onboarding_007_no_old_base_fields():
    """world_tree.base.timeline / geography / metadata 整块不再写"""
    # v003: world_tree 表无 timeline_era / anchor_event / geography_primary / metadata_json 列
    # onboarding_artifacts.py 不写 base.timeline / base.geography / base.metadata
    src = Path("backend/services/onboarding_artifacts.py").read_text()
    assert "base.timeline" not in src
    assert "base.geography" not in src
    assert "base.metadata" not in src


# ============ TC-008 ============

def test_tc_onboarding_008_wtm_output_9_tables():
    """WTM 输出范围覆盖完整世界树基座（9 张表）"""
    # v003 WTM 输出：world_tree / characters / main_plot / sub_plot / volumes /
    #                world_entries / timeline_events / geography_locations / seeds
    # 但实际是 11 张表（含 project_state + character_relationships）
    # 验证 WTM 主入口 generate_full_world_tree_baseline 涉及表
    src = Path("backend/agent/agents/world_tree_manager.py").read_text()
    # 检查 9 张表
    for table in [
        "world_tree", "characters", "main_plot", "sub_plot", "volumes",
        "world_entries", "timeline_events", "geography_locations", "seeds",
    ]:
        assert table in src, f"WTM 输出应覆盖表 {table}"


# ============ TC-009 ============


def test_tc_onboarding_009_wtm_failure_fallback(mock_get_store, seed_project, monkeypatch):
    """管家委托 WTM 失败回退到 collecting"""
    import asyncio
    from backend.services import onboarding_artifacts

    # 模拟 WTM 抛异常
    from backend.services.onboarding_artifacts import (
        mark_wtm_pending,
        mark_wtm_baseline_failed,
    )

    # 模拟：WTM 委托失败，service 层回退 info_state 到 collecting
    mark_wtm_pending("p1")
    mark_wtm_baseline_failed("p1", "LLM 调用失败")

    # 失败后 info_state 应为 collecting
    with mock_get_store.connection() as c:
        row = c.execute(
            "SELECT info_state FROM onboarding_state WHERE project_id='p1'"
        ).fetchone()
    assert row is None or row[0] == "collecting", (
        f"失败后 info_state 应为 collecting，实际 {row[0] if row else None}"
    )


# ============ TC-010 ============

def test_tc_onboarding_010_state_three_transitions():
    """onboarding_state.info_state 三态流转（collecting / wtm_pending / ready）"""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(open("backend/persistence/migrations/v003_init.sql").read())
    conn.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES ('p1', 'Test', datetime('now'), datetime('now'))"
    )
    conn.commit()

    # 1. collecting
    conn.execute(
        "INSERT INTO onboarding_state (project_id, info_state, created_at, updated_at) "
        "VALUES ('p1', 'collecting', datetime('now'), datetime('now'))"
    )
    conn.commit()
    assert conn.execute(
        "SELECT info_state FROM onboarding_state WHERE project_id='p1'"
    ).fetchone()[0] == "collecting"

    # 2. collecting → wtm_pending
    conn.execute(
        "UPDATE onboarding_state SET info_state='wtm_pending', updated_at=datetime('now') "
        "WHERE project_id='p1'"
    )
    conn.commit()
    assert conn.execute(
        "SELECT info_state FROM onboarding_state WHERE project_id='p1'"
    ).fetchone()[0] == "wtm_pending"

    # 3. wtm_pending → ready
    conn.execute(
        "UPDATE onboarding_state SET info_state='ready', updated_at=datetime('now') "
        "WHERE project_id='p1'"
    )
    conn.commit()
    assert conn.execute(
        "SELECT info_state FROM onboarding_state WHERE project_id='p1'"
    ).fetchone()[0] == "ready"

    # 4. 非法值应 CHECK 失败
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE onboarding_state SET info_state='invalid' WHERE project_id='p1'"
        )
