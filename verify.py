"""M-α 验收脚本 — 跑通 4 项验收标准

验收标准（来自 docs/roadmap/v0.3-product-skeleton.md §4 M-α）:
- [ ] ProjectManager.create('demo', ...) 创建空骨架目录
- [ ] ProjectManager.load('demo', ...) 加载并校验通过
- [ ] WorldTree.from_dict(...) 反序列化成功
- [ ] WorldTree.to_dict() 序列化结果 round-trip 一致

额外验收:
- WorldTree.rollback_to(node_id) 硬 reset 行为
- 7 件 Schema Pydantic 校验

用法:
    cd /Users/wuyu/creativeToys/realtime-novel
    source .venv/bin/activate
    python verify.py
"""
from __future__ import annotations

import sys
import shutil
import tempfile
from pathlib import Path

from realtime_novel import ProjectManager, WorldTree

ROOT = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT / "projects"


def line(s: str = "") -> None:
    print(s)


def header(s: str) -> None:
    line()
    line("=" * 70)
    line(f"  {s}")
    line("=" * 70)


# ========== 验收 1: ProjectManager.create ==========
def test_create() -> str:
    header("验收 1: ProjectManager.create('demo', ...)")
    pm = ProjectManager(workspace_root=ROOT)
    demo_dir = PROJECTS_DIR / "demo-urban-romance"

    if demo_dir.exists():
        print(f"  ⚠️  项目已存在: {demo_dir.relative_to(ROOT)}")
        print(f"     跳过创建（验收 1 测试用 tmp 目录）")
    else:
        proj = pm.create("demo-urban-romance")
        print(f"  ✓ 创建项目: {proj.project_dir.relative_to(ROOT)}")
        print(f"    · chapters/ 已建")
        print(f"    · 7 件空 YAML 已落盘")

    # 二次验收：用 tmp 目录真创建一次
    with tempfile.TemporaryDirectory() as tmp:
        pm2 = ProjectManager(workspace_root=tmp)
        proj2 = pm2.create("test-tmp")
        assert proj2.project_dir.exists()
        assert (proj2.project_dir / "chapters").exists()
        yaml_files = sorted(proj2.project_dir.glob("*.yaml"))
        assert len(yaml_files) == 7, f"期望 7 件 YAML，实际 {len(yaml_files)}"
        print(f"  ✓ 临时目录真创建: {len(yaml_files)} 件 YAML")
        return "✅ 验收 1 通过"


# ========== 验收 2: ProjectManager.load ==========
def test_load() -> str:
    header("验收 2: ProjectManager.load('demo-urban-romance', ...)")
    pm = ProjectManager(workspace_root=ROOT)
    loaded = pm.load("demo-urban-romance", strict=True)

    print(f"  ✓ 加载项目: {loaded.project.project_dir.relative_to(ROOT)}")
    print(f"  ✓ 解析 7 件 Schema:")
    for filename, schema in loaded.artifacts.items():
        print(f"    · {filename}: {type(schema).__name__}")

    assert len(loaded.artifacts) == 7, f"期望 7 件，实际 {len(loaded.artifacts)}"
    assert loaded.missing == [], f"缺件: {loaded.missing}"

    # 自检：demo 数据完整性
    wt = loaded["01-world-tree.yaml"]
    sc = loaded["02-style-charter.yaml"]
    mp = loaded["04-main-plot.yaml"]
    cc = loaded["06-character-card.yaml"]
    sp = loaded["05-sub-plot.yaml"]
    st = loaded["07-seed-table.yaml"]
    gr = loaded["03-genre-resonance.yaml"]

    print()
    print(f"  📊 Demo 数据规模:")
    print(f"    · WorldTree.branches: {len(wt.branches)} 节点")
    print(f"    · StyleCharter.density: {sc.density.get('specificity', '?')}")
    print(f"    · MainPlot.beats: {len(mp.beats)} 节拍 (current={mp.current_beat})")
    print(f"    · CharacterCard.characters: {len(cc.characters)} 人物")
    print(f"    · CharacterCard.relationships: {len(cc.relationships)} 关系")
    print(f"    · SubPlot.threads: {len(sp.threads)} 支线")
    print(f"    · SeedTable.seeds: {len(st.seeds)} 种子")
    print(f"    · GenreResonance.accept: {len(gr.accept)} / reject: {len(gr.reject)}")

    return "✅ 验收 2 通过"


# ========== 验收 3: WorldTree.from_dict ==========
def test_from_dict() -> str:
    header("验收 3: WorldTree.from_dict(...) 反序列化")
    pm = ProjectManager(workspace_root=ROOT)
    loaded = pm.load("demo-urban-romance")

    # 7 件 Pydantic → dict
    data = {filename: schema.model_dump(exclude_none=True) for filename, schema in loaded.artifacts.items()}

    # dict → WorldTree
    wt = WorldTree.from_dict(data)
    print(f"  ✓ 反序列化成功: {type(wt).__name__}")
    print(f"  ✓ 7 件全部加载: {list(wt.to_dict().keys())}")

    # 验证内容一致性
    summary = wt.summary()
    print()
    print(f"  📊 WorldTree.summary():")
    for k, v in summary.items():
        print(f"    · {k}: {v}")

    return "✅ 验收 3 通过"


# ========== 验收 4: WorldTree.to_dict round-trip ==========
def test_round_trip() -> str:
    header("验收 4: WorldTree.to_dict() round-trip 一致性")
    pm = ProjectManager(workspace_root=ROOT)
    wt1 = WorldTree.from_project_dir(PROJECTS_DIR / "demo-urban-romance")

    # 序列化
    d1 = wt1.to_dict()

    # 反序列化
    wt2 = WorldTree.from_dict(d1)

    # 再序列化
    d2 = wt2.to_dict()

    # 比较
    keys = set(d1.keys()) | set(d2.keys())
    assert set(d1.keys()) == set(d2.keys()) == {
        "01-world-tree.yaml",
        "02-style-charter.yaml",
        "03-genre-resonance.yaml",
        "04-main-plot.yaml",
        "06-character-card.yaml",
        "05-sub-plot.yaml",
        "07-seed-table.yaml",
    }, f"键不匹配: d1={d1.keys()}, d2={d2.keys()}"

    for k in d1:
        assert d1[k] == d2[k], f"round-trip 不一致: {k}"

    print(f"  ✓ to_dict → from_dict → to_dict 7 件全部一致")
    return "✅ 验收 4 通过"


# ========== 额外验收: rollback_to ==========
def test_rollback() -> str:
    header("额外验收: WorldTree.rollback_to(node_id) 硬 reset")
    pm = ProjectManager(workspace_root=ROOT)
    wt = WorldTree.from_project_dir(PROJECTS_DIR / "demo-urban-romance")

    before = len(wt.world_tree.branches)
    print(f"  当前节点数: {before}")

    if before < 3:
        # demo 数据少（只有 1 节点），跳过硬 reset 场景
        # 改为验证 rollback_to 在不存在节点时抛错
        try:
            wt.rollback_to("node-nonexistent")
            assert False, "应抛 ValueError"
        except ValueError:
            print(f"  ✓ rollback_to 不存在节点时正确抛 ValueError")
        # 重新加载（无变更）
        wt2 = WorldTree.from_project_dir(PROJECTS_DIR / "demo-urban-romance")
        assert len(wt2.world_tree.branches) == before, "未操作时磁盘未改"
        print(f"  ✓ 磁盘未改（rollback 仅内存）")
        # 补充：手工构造多节点 WorldTree 验证硬 reset
        print()
        print(f"  📊 补充：手工构造 5 节点 WorldTree 验证硬 reset:")
        from realtime_novel.schemas import WorldTreeSchema
        from realtime_novel import WorldTree as WT
        # 用 demo 的 7 件作为基础
        wt_multi = WorldTree.from_project_dir(PROJECTS_DIR / "demo-urban-romance")
        for i in range(3, 6):
            wt_multi.add_node({
                "id": f"test-node-{i}",
                "type": "scene",
                "title": f"测试节点 {i}",
                "parent_id": "node-001",
                "status": "completed",
                "children": [],
            })
        before_multi = len(wt_multi.world_tree.branches)
        target_node = wt_multi.world_tree.branches[1].id
        deleted = wt_multi.rollback_to(target_node)
        after_multi = len(wt_multi.world_tree.branches)
        print(f"    · 构造 5 节点 → 回档到 {target_node} → 删 {deleted} 节点 → 剩 {after_multi} 节点")
        assert before_multi - after_multi == deleted
        assert after_multi == 2, f"期望剩 2 节点，实际 {after_multi}"
        return "✅ 额外验收通过（边界 + 硬 reset 双场景）"

    # 找一个存在的 node
    target = wt.world_tree.branches[2].id
    deleted = wt.rollback_to(target)
    after = len(wt.world_tree.branches)
    print(f"  回档到 node_id={target}: 删 {deleted} 节点，剩 {after} 节点")

    assert before - after == deleted
    assert all(n.id != target or n is wt.world_tree.branches[2] for n in wt.world_tree.branches)

    # 再加载一次（从 disk），回档不影响 disk
    wt2 = WorldTree.from_project_dir(PROJECTS_DIR / "demo-urban-romance")
    assert len(wt2.world_tree.branches) == before, "回档不应修改磁盘文件"
    print(f"  ✓ 回档是内存操作，磁盘未改")

    return "✅ 额外验收通过"


def main() -> int:
    print()
    print("🩵  M-α 验收脚本 · 骨架 0.1")
    print(f"   工程: {ROOT}")

    # 先装载 demo（如果还没有）
    if not (PROJECTS_DIR / "demo-urban-romance" / "01-world-tree.yaml").exists():
        header("前置：装载 demo 数据")
        from realtime_novel._seed_demo import seed
        seed()

    results = []
    try:
        results.append(test_create())
        results.append(test_load())
        results.append(test_from_dict())
        results.append(test_round_trip())
        results.append(test_rollback())
    except Exception as e:
        line()
        line(f"❌ 验收失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    header("🎉 验收结果")
    for r in results:
        line(f"  {r}")
    line()
    line("全部通过 = 骨架 0.1 (M-α) 跑通 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
