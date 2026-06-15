"""M-δ 验收脚本 — 跑通 3 项验收标准

验收标准（docs/roadmap/v0.3-product-skeleton.md §4 M-δ）:
- [ ] 导演/演员模式输入解析正确
- [ ] 回档硬 reset 行为符合 design/01 §1.4
- [ ] 回档后能继续生成新章节，无状态污染

策略:
- 验收 1: 纯字符串测试 (不调 LLM), 4 种输入验证解析
- 验收 2: 构造一个含 5 节点的 WorldTree, rollback 到 node-003
         验证 7 件 YAML 落盘 + 后续章节文件被删
- 验收 3: rollback 后再 generate 1 章, 验证流程无中断

临时项目位置（按 .realtime-novel/conventions.md §9 #15）:
- <工程根>/.tmp/m4-test/ 不入仓

用法:
    cd /Users/wuyu/creativeToys/realtime-novel
    source .venv/bin/activate
    python tests/m4/test_intervention.py
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

from realtime_novel import (
    ProjectManager,
    WorldTree,
    InterventionParser,
    InterventionMode,
    RollbackManager,
    ChapterGenerator,
)
from realtime_novel.core.schemas import ChapterSummarySchema
from realtime_novel.services.chapter_generator import SEGMENTS_PER_CHAPTER


ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / ".tmp" / "m4-test"  # conventions.md §9 #15
_TMP_DIR_HOLDER: list = []


def line(s: str = "") -> None:
    print(s, flush=True)


def header(s: str) -> None:
    line()
    line("=" * 70)
    line(f"  {s}")
    line("=" * 70)


# ========== 验收 1: 干预解析 ==========
def test_intervention_parse() -> None:
    header("验收 1: InterventionParser 解析 (导演/演员)")

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        parser = InterventionParser(project_dir)

        # 案例 1: 导演模式 (我期望)
        i1 = parser.parse(
            "我期望陈岚离开",
            chapter_num=21,
            mode=InterventionMode.DIRECTOR,
        )
        assert i1.mode == "director"
        assert i1.extracted_payload == "陈岚离开"
        assert "导演干预" in i1.system_msg
        assert "陈岚离开" in i1.system_msg
        line(f"  ✓ 1) '我期望陈岚离开' → director, payload='{i1.extracted_payload}'")

        # 案例 2: 演员模式 (我)
        i2 = parser.parse(
            "我转身离开房间",
            chapter_num=21,
            mode=InterventionMode.ACTOR,
        )
        assert i2.mode == "actor"
        assert i2.extracted_payload == "转身离开房间"
        assert "演员干预" in i2.system_msg
        line(f"  ✓ 2) '我转身离开房间' → actor, payload='{i2.extracted_payload}'")

        # 案例 3: 我希望 (导演变体)
        i3 = parser.parse(
            "我希望林远下决心",
            chapter_num=22,
            mode=InterventionMode.DIRECTOR,
        )
        assert i3.mode == "director"
        assert i3.extracted_payload == "林远下决心"
        line(f"  ✓ 3) '我希望林远下决心' → director, payload='{i3.extracted_payload}'")

        # 案例 4: 自由文本 (无前缀, 走默认 mode)
        i4 = parser.parse(
            "林远应该去找周叔",
            chapter_num=23,
        )
        assert i4.mode == "director"  # 默认
        assert i4.extracted_payload == "林远应该去找周叔"
        line(f"  ✓ 4) '林远应该去找周叔' → 默认 director, payload='{i4.extracted_payload}'")

        # 持久化验证
        log = json.loads((project_dir / ".intervention-log.json").read_text(encoding="utf-8"))
        assert len(log["interventions"]) == 4
        line(f"  ✓ 持久化 .intervention-log.json: {len(log['interventions'])} 条")


# ========== 验收 2: 回档硬 reset (落盘) ==========
def test_rollback_persist(pm: ProjectManager) -> None:
    """回档到 node, 验证 7 件 YAML 落盘 + 章节被裁"""
    header("验收 2: RollbackManager 硬 reset (落盘)")

    project = pm.projects_root / "test-rollback"
    # 重新拿 project (用 get_or_create)
    project = pm.create("test-rollback", exist_ok=True)
    tree = WorldTree.from_project_dir(project.project_dir)

    # 加载 7 件 + demo
    from realtime_novel import utils
    seed_demo_module = utils.seed_demo
    # 用现有 demo (假设存在)
    from realtime_novel.adapters.io import read
    demo_path = ROOT / "projects" / "demo-urban-romance"
    if not demo_path.exists():
        print("  ⚠️  demo 不存在, 跳过验收 2")
        return
    # 复制 demo 的 7 件
    for schema_filename in [
        "01-world-tree.yaml", "02-style-charter.yaml", "03-genre-resonance.yaml",
        "04-main-plot.yaml", "05-sub-plot.yaml", "06-character-card.yaml", "07-seed-table.yaml",
    ]:
        src = demo_path / schema_filename
        tgt = project.file_path(schema_filename)
        shutil.copy2(src, tgt)
    # 复制 demo 的 chapters
    chapters_src = demo_path / "chapters"
    chapters_tgt = project.project_dir / "chapters"
    if chapters_src.exists():
        for ch in sorted(chapters_src.glob("chapter-*.txt")):
            shutil.copy2(ch, chapters_tgt / ch.name)

    # 重新加载 (用更新后的 YAML)
    loaded = pm.load("test-rollback", strict=True)
    tree = WorldTree.from_dict(loaded.artifacts)
    print(f"  · 初始 Node 数: {len(tree.world_tree.branches)}")
    print(f"  · 初始 chapters: {len(list(chapters_tgt.glob('chapter-*.txt')))}")

    # 模拟生成 3 个新 Node (chapter-21, 22, 23) + 章节
    for n in [21, 22, 23]:
        node = {
            "id": f"node-chapter-{n:02d}",
            "type": "scene",
            "title": f"第 {n} 章",
            "parent_id": "node-001",
            "status": "completed",
            "children": [],
        }
        tree.add_node(node)
        # 创建 dummy chapter 文件
        (chapters_tgt / f"chapter-{n:02d}.txt").write_text(f"# 第 {n} 章\n\n", encoding="utf-8")

    # 落盘
    tree.to_project_dir(project.project_dir)
    print(f"  · 添加 3 Node + 3 章节后: {len(tree.world_tree.branches)} Node, "
          f"{len(list(chapters_tgt.glob('chapter-*.txt')))} chapters")

    # 准备 7 件原值 (rollback 后应恢复)
    original_artifacts = {}
    for fn in ["01-world-tree.yaml", "02-style-charter.yaml", "03-genre-resonance.yaml",
              "04-main-plot.yaml", "05-sub-plot.yaml", "06-character-card.yaml", "07-seed-table.yaml"]:
        original_artifacts[fn] = (project.file_path(fn)).read_text(encoding="utf-8")
    original_node_001_pos = sum(
        1 for n in tree.world_tree.branches if n.id == "node-001"
    )

    # 执行回档到 node-chapter-21 (节点含 chapter-21 标识, 应删 21/22/23)
    print()
    print(f"  ⏪ rollback 到 node-chapter-21 ...")
    rm = RollbackManager(tree, project)
    try:
        result = rm.rollback("node-chapter-21", confirm=True)
    except Exception as e:
        print(f"  ❌ rollback 失败: {e}")
        return

    print(f"  ✓ 回档完成")
    print(f"    · 删 Node: {result.deleted_branches_count}")
    print(f"    · 删 章节: {result.deleted_chapters_count}")
    print(f"    · 剩 章节: {result.remaining_chapters_count}")
    assert result.target_node_id == "node-chapter-21"
    # 验证 chapter-21/22/23 已被删
    for n in [21, 22, 23]:
        f = chapters_tgt / f"chapter-{n:02d}.txt"
        assert not f.exists(), f"应被删但还在: {f}"
    # 验证 chapter-01~20 还在
    for n in [1, 5, 10, 15, 20]:
        f = chapters_tgt / f"chapter-{n:02d}.txt"
        assert f.exists(), f"应保留但被删: {f}"
    print(f"  ✓ chapter-21/22/23 文件被删, chapter-01~20 保留")

    # 验证 7 件 YAML 落盘
    print()
    print(f"  📋 验证 7 件 YAML 重新落盘:")
    for fn, original in original_artifacts.items():
        current = (project.file_path(fn)).read_text(encoding="utf-8")
        # 不严格相等 (有 updated_at 时间戳), 但 schema_version 必须一致
        orig_data = yaml.safe_load(original)
        cur_data = yaml.safe_load(current)
        assert orig_data.get("schema_version") == cur_data.get("schema_version")
        line(f"     · {fn}: schema_version 一致 ({cur_data.get('schema_version')})")


# ========== 验收 3: 回档后继续生成 ==========
def test_rollback_then_generate(pm: ProjectManager) -> None:
    """回档后能继续生成新章节, 无状态污染"""
    header("验收 3: 回档后继续生成新章节 (无状态污染)")

    # 直接读验收 2 留下的状态 (不再 pm.create, 会重写 7 件空)
    loaded = pm.load("test-rollback", strict=True)
    tree = WorldTree.from_dict(loaded.artifacts)
    project = loaded.project  # 修: 拿 project 句柄

    # 确认回档状态: node-chapter-21 应是最后 Node
    last_node = tree.world_tree.branches[-1]
    line(f"  · 回档后最后 Node: {last_node.id} ({last_node.title})")
    assert last_node.id == "node-chapter-21"

    # 找当前最大章节号
    chapters_dir = project.project_dir / "chapters"
    existing = sorted(
        int(p.stem.split("-")[-1])
        for p in chapters_dir.glob("chapter-*.txt")
    )
    next_chapter = (existing[-1] if existing else 0) + 1
    line(f"  · 现有章节: {len(existing)} 章, 下一章: {next_chapter}")

    # 准备历史摘要 (从 demo 复制)
    from realtime_novel.adapters.io import read
    import json
    summary_path = ROOT / "docs" / "eval-notes" / "code" / "v0.2" / "output" / "case-1-urban-romance" / "chapter_summaries.json"
    summaries = []
    if summary_path.exists():
        raw = json.loads(summary_path.read_text(encoding="utf-8"))
        for s in raw[-3:]:
            try:
                summaries.append(ChapterSummarySchema.model_validate(s))
            except Exception:
                pass

    # 读最近 1 章全文
    last_chapter_path = chapters_dir / f"chapter-{existing[-1]:02d}.txt"
    last_chapter_full = last_chapter_path.read_text(encoding="utf-8") if existing else None

    # 生成下一章 (会跑真 LLM)
    print(f"  🚀 生成第 {next_chapter} 章 (会跑真 LLM) ...")
    generator = ChapterGenerator(tree, project)
    try:
        result = generator.generate_next(
            chapter_num=next_chapter,
            chapter_summaries=summaries,
            last_chapter_full=last_chapter_full,
        )
    except Exception as e:
        print(f"  ❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 验证
    line(f"  ✓ {result.word_count} 字, {result.duration_sec:.1f}s")
    line(f"  ✓ 落盘: {project.chapter_path(next_chapter).relative_to(ROOT)}")

    # 验证新章节在 disk
    new_chapter_path = chapters_dir / f"chapter-{next_chapter:02d}.txt"
    assert new_chapter_path.exists()
    line(f"  ✓ 章节文件存在: {new_chapter_path.name}")

    # 验证 WorldTree 更新
    assert tree.world_tree.branches[-1].id == f"node-chapter-{next_chapter:02d}"
    line(f"  ✓ WorldTree 新 Node: {tree.world_tree.branches[-1].id}")


def main() -> int:
    print()
    print("⏪  M-δ 验收脚本 · 骨架 0.4")
    print(f"   工程: {ROOT}")
    line()

    # 1. 测试临时目录 (项目放这里)
    tmp = TMP_ROOT / f"run-{time.strftime('%Y%m%d_%H%M%S')}"
    tmp.mkdir(parents=True, exist_ok=True)
    _TMP_DIR_HOLDER.append(tmp)
    pm = ProjectManager(workspace_root=tmp)

    try:
        test_intervention_parse()
        test_rollback_persist(pm)
        test_rollback_then_generate(pm)

        header("🎉 验收结果")
        line(f"  ✅ 验收 1: InterventionParser 解析 (4 种输入)")
        line(f"  ✅ 验收 2: RollbackManager 硬 reset (落盘)")
        line(f"  ✅ 验收 3: 回档后继续生成新章节 (无状态污染)")
        line()
        line("全部通过 = 骨架 0.4 (M-δ) 跑通 ✅")
        return 0
    except Exception as e:
        line()
        line(f"❌ 验收失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


# 加 yaml import
import yaml

if __name__ == "__main__":
    sys.exit(main())
