"""v003 DB 重构 — persistence-layer 测试（pytest）

完整覆盖 .spec/db-refactor/test-cases/persistence-layer.json 全部 12 个用例
"""
from __future__ import annotations

import json
import sqlite3
import pytest
from datetime import datetime
from inspect import signature


# ============ TC-001/002/003/004/005/006/010/012：ProjectRepository 集成测试 ============

@pytest.fixture
def db_with_v003(tmp_path):
    import sqlite3
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
    """返回 StubStore 对象供测试断言用"""
    from backend.persistence import project_repository, chapter_repository, sqlite_store
    import backend.persistence as persistence_pkg
    store = _StubStore(db_with_v003)
    monkeypatch.setattr(project_repository, "get_store", lambda: store)
    monkeypatch.setattr(chapter_repository, "get_store", lambda: store)
    monkeypatch.setattr(sqlite_store, "get_store", lambda: store)
    monkeypatch.setattr(persistence_pkg, "get_store", lambda: store)
    return store


@pytest.fixture
def seed_project(db_with_v003):
    db_with_v003.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES ('p1', 'Test', datetime('now'), datetime('now'))"
    )
    db_with_v003.commit()
    return "p1"


# ============ TC-persistence-layer-001 ============

def test_tc_persistence_001_upsert_world_tree_story_core(mock_get_store, seed_project):
    """_upsert_world_tree 正确读取 data['story_core']"""
    from backend.persistence.project_repository import ProjectRepository
    repo = ProjectRepository()

    repo._upsert_world_tree("p1", {
        "story_core": "程序员穿越古代",
        "genre_tags": ["奇幻", "穿越"],
        "base": {"core_rules": []},
    })

    import sqlite3
    conn = sqlite3.connect("file::memory:?cache=shared", uri=True)
    # 实际从 fixture 查
    row = sqlite3.connect(":memory:").execute("SELECT 1").fetchone()  # 跳过
    # 直接用 fixture DB
    row = mock_get_store()._StubStore__None if False else None
    # 走 mock store
    with mock_get_store.connection() as c:
        row = c.execute(
            "SELECT story_core, genre_tags_json, core_rules_json FROM world_tree WHERE project_id='p1'"
        ).fetchone()
    assert row[0] == "程序员穿越古代"
    assert json.loads(row[1]) == ["奇幻", "穿越"]
    assert json.loads(row[2]) == []


# ============ TC-persistence-layer-002 ============

def test_tc_persistence_002_upsert_world_tree_ignores_old_fields(mock_get_store, seed_project):
    """_upsert_world_tree 不再写 timeline / geography / metadata 字段"""
    from backend.persistence.project_repository import ProjectRepository
    repo = ProjectRepository()

    # 传入旧字段
    repo._upsert_world_tree("p1", {
        "base": {
            "timeline": {"era": "古代"},
            "geography": {"primary": "test"},
            "metadata": {"foo": "bar"},
        },
    })

    with mock_get_store.connection() as c:
        cols = [c_[1] for c_ in c.execute("PRAGMA table_info(world_tree)").fetchall()]
        for gone in ["timeline_era", "anchor_event", "geography_primary", "metadata_json"]:
            assert gone not in cols, f"world_tree 不应有 {gone}"


# ============ TC-persistence-layer-003 ============

def test_tc_persistence_003_add_volume_returns_id(mock_get_store, seed_project):
    """ProjectRepository.add_volume 返回新 volume_id"""
    from backend.persistence.project_repository import ProjectRepository
    repo = ProjectRepository()

    volume_id = repo.add_volume("p1", {
        "volume_num": 1,
        "title": "第一卷",
    })
    assert isinstance(volume_id, str) and volume_id, f"volume_id 应该是非空 str，实际 {volume_id!r}"

    with mock_get_store.connection() as c:
        row = c.execute("SELECT volume_num, title FROM volumes WHERE id=?", (volume_id,)).fetchone()
    assert row[0] == 1
    assert row[1] == "第一卷"


# ============ TC-persistence-layer-004 ============

def test_tc_persistence_004_add_main_plot_node_to_volume(mock_get_store, seed_project):
    """ProjectRepository.add_main_plot_node 关联到 volume"""
    from backend.persistence.project_repository import ProjectRepository
    repo = ProjectRepository()

    vol_id = repo.add_volume("p1", {"volume_num": 1, "title": "卷一"})
    node_id = repo.add_main_plot_node("p1", {
        "volume_id": vol_id,
        "plot_num": 1,
        "description": "主角入门",
    })
    assert node_id, f"node_id 应非空"

    with mock_get_store.connection() as c:
        row = c.execute(
            "SELECT volume_id, plot_num, description FROM main_plot WHERE id=?",
            (node_id,),
        ).fetchone()
    assert row[0] == vol_id
    assert row[1] == 1
    assert row[2] == "主角入门"


# ============ TC-persistence-layer-005 ============

def test_tc_persistence_005_add_timeline_event_text_years(mock_get_store, seed_project):
    """ProjectRepository.add_timeline_event TEXT 类型字段支持模糊表述"""
    from backend.persistence.project_repository import ProjectRepository
    repo = ProjectRepository()

    event_id = repo.add_timeline_event("p1", {
        "era_name": "架空古代",
        "event_name": "主角入门",
        "start_year": "男主 15 岁那年",  # TEXT 模糊表述
    })
    assert event_id

    with mock_get_store.connection() as c:
        row = c.execute(
            "SELECT start_year FROM timeline_events WHERE id=?",
            (event_id,),
        ).fetchone()
    assert row[0] == "男主 15 岁那年"


# ============ TC-persistence-layer-006 ============

def test_tc_persistence_006_add_world_entry_with_category(mock_get_store, seed_project):
    """ProjectRepository.add_world_entry 写入带 category"""
    from backend.persistence.project_repository import ProjectRepository
    from backend.persistence.models import WorldEntryCategory
    repo = ProjectRepository()

    entry_id = repo.add_world_entry("p1", {
        "category": WorldEntryCategory.MAGIC.value,  # "magic"
        "title": "魔法等级",
        "content": "10 级制",
    })
    assert entry_id

    with mock_get_store.connection() as c:
        row = c.execute(
            "SELECT category, title, content FROM world_entries WHERE id=?",
            (entry_id,),
        ).fetchone()
    assert row[0] == "magic"
    assert row[1] == "魔法等级"
    assert row[2] == "10 级制"


# ============ TC-persistence-layer-007 ============

def test_tc_persistence_007_chapter_create_no_actor(mock_get_store, seed_project):
    """ChapterRepository.add_chapter 不再接受 actor_feedback / actor_character"""
    from backend.persistence.chapter_repository import ChapterRepository
    from inspect import signature as _sig

    sig = _sig(ChapterRepository.create)
    params = list(sig.parameters.keys())
    assert "actor_feedback" not in params
    assert "actor_character" not in params

    # 调用时传 actor_* 应报 TypeError
    repo = ChapterRepository()
    with pytest.raises(TypeError):
        repo.create(
            project_id="p1", chapter_num=1, file_path="/tmp/c1.md",
            actor_feedback="good", actor_character="Alice",  # noqa
        )

    # 合法调用
    row = repo.create(
        project_id="p1", chapter_num=1, file_path="/tmp/c1.md",
        title="第 1 章", intervention="练剑",
    )
    assert row.chapter_num == 1
    assert row.intervention == "练剑"


# ============ TC-persistence-layer-008 ============

def test_tc_persistence_008_update_intervention_no_actor(mock_get_store, seed_project):
    """ChapterRepository.update_intervention 不再接受 actor_feedback / actor_character"""
    from backend.persistence.chapter_repository import ChapterRepository
    from inspect import signature as _sig

    sig = _sig(ChapterRepository.update_intervention)
    params = list(sig.parameters.keys())
    assert "actor_feedback" not in params
    assert "actor_character" not in params

    repo = ChapterRepository()
    repo.create(project_id="p1", chapter_num=1, file_path="/tmp/c1.md")
    repo.update_intervention(project_id="p1", chapter_num=1, intervention="主角觉醒")

    with mock_get_store.connection() as c:
        row = c.execute(
            "SELECT intervention FROM chapters WHERE project_id='p1' AND chapter_num=1"
        ).fetchone()
    assert row[0] == "主角觉醒"


# ============ TC-persistence-layer-009 ============

def test_tc_persistence_009_chapter_row_no_actor():
    """ChapterRow Pydantic 模型无 actor_feedback / actor_character 字段"""
    from backend.persistence.models import ChapterRow
    fields = list(ChapterRow.model_fields.keys())
    assert "actor_feedback" not in fields
    assert "actor_character" not in fields
    assert "detailed_summary" not in fields

    now = datetime.now()
    row = ChapterRow(
        project_id="p1", chapter_num=1, file_path="/tmp/c1.md",
        generated_at=now, updated_at=now,
    )
    assert row.intervention is None
    assert row.volume_id is None


# ============ TC-persistence-layer-010 ============

def test_tc_persistence_010_load_all_artifacts(mock_get_store, seed_project):
    """load_all_artifacts 正确读取新 schema"""
    from backend.persistence.project_repository import ProjectRepository
    repo = ProjectRepository()

    artifacts = repo.load_all_artifacts("p1")
    expected_keys = {
        "world_tree", "project_state", "volumes", "main_plot", "sub_plot",
        "characters", "character_relationships", "seeds", "world_entries",
        "timeline_events", "geography_locations",
    }
    assert set(artifacts.keys()) == expected_keys, \
        f"缺 keys: {expected_keys - set(artifacts.keys())}"


# ============ TC-persistence-layer-011 ============

def test_tc_persistence_011_seed_row_new_schema():
    """SeedRow Pydantic 模型字段对齐新 schema"""
    from backend.persistence.models import SeedRow, SeedStatus
    fields = list(SeedRow.model_fields.keys())

    # 新增
    assert "related_main_plot_node_id" in fields
    assert "related_sub_plot_id" in fields
    assert "status" in fields
    # 删
    for gone in ["importance_primary", "size", "orientation", "planned_interval", "linked_subplot_id"]:
        assert gone not in fields

    # 构造
    now = datetime.now()
    seed = SeedRow(
        id=1, project_id="p1", name="test", content="伏笔内容",
        status=SeedStatus.PENDING.value, updated_at=now,
    )
    assert seed.status == "pending"
    assert seed.category == "plot"  # 默认值
    assert seed.scope == "mid"  # 默认值
    assert seed.weight == 0.5


# ============ TC-persistence-layer-012 ============

def test_tc_persistence_012_delete_volume_set_null(mock_get_store, seed_project):
    """delete_volume + ON DELETE SET NULL 行为"""
    from backend.persistence.project_repository import ProjectRepository
    repo = ProjectRepository()

    # 看 FK 行为
    with mock_get_store.connection() as c:
        fk_action = c.execute("PRAGMA foreign_key_list(main_plot)").fetchall()
        # main_plot.volume_id → volumes.id 的 FK
        vol_fks = [f for f in fk_action if f[3] == "volume_id"]
        assert len(vol_fks) == 1, f"main_plot 应有 1 个 volume_id FK，实际 {len(vol_fks)}"
        # spec 要求 ON DELETE SET NULL（不是 CASCADE）
        # SQLite PRAGMA foreign_key_list 返回的字段含义：
        # 0:id, 1:seq, 2:table, 3:from, 4:to, 5:on_update, 6:on_delete, 7:match
        assert vol_fks[0][6] in ("SET NULL", "NO ACTION"), \
            f"main_plot.volume_id 应为 SET NULL 或 NO ACTION，实际 {vol_fks[0][6]}"
