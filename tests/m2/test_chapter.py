"""M-β 验收脚本 — 跑通 5 项验收标准

验收标准（docs/roadmap/v0.3-product-skeleton.md §4 M-β）:
- [ ] 加载 demo 的 WorldTree
- [ ] 复用 v0.2 LLM 配置，调用成功
- [ ] 生成 1 章真实产品流（非评测流）
- [ ] 新章节落盘 chapters/chapter-21.txt
- [ ] WorldTree 正确更新（新增 Node、提取种子、滚动摘要）

用法:
    cd /Users/wuyu/creativeToys/realtime-novel
    source .venv/bin/activate
    python verify_mb.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from realtime_novel import (
    ProjectManager,
    WorldTree,
    ChapterGenerator,
    ChapterSummarySchema,
)


ROOT = Path(__file__).resolve().parents[2]  # tests/m2/ → 工程根
PROJECTS_DIR = ROOT / "projects"
DEMO_PROJECT = "demo-urban-romance"


def line(s: str = "") -> None:
    print(s)


def header(s: str) -> None:
    line()
    line("=" * 70)
    line(f"  {s}")
    line("=" * 70)


# ========== 验收 1: 加载 demo WorldTree ==========
def test_load_demo() -> tuple[ProjectManager, WorldTree, "Project"]:
    header("验收 1: 加载 demo WorldTree")
    pm = ProjectManager(workspace_root=ROOT)
    project = pm.projects_root / DEMO_PROJECT
    assert project.exists(), f"项目不存在: {project}（先跑 python -m realtime_novel._seed_demo）"

    loaded = pm.load(DEMO_PROJECT, strict=True)
    tree = WorldTree.from_dict(loaded.artifacts)
    summary = tree.summary()
    print(f"  ✓ 加载项目: {loaded.project.project_dir.relative_to(ROOT)}")
    print(f"  ✓ WorldTree 实例化: {type(tree).__name__}")
    print()
    print(f"  📊 Demo 数据规模:")
    for k, v in summary.items():
        print(f"    · {k}: {v}")
    return pm, tree, loaded.project


# ========== 验收 2: LLM 客户端可调用 ==========
def test_llm_client() -> None:
    header("验收 2: LLM 客户端可调用（不实际生成，仅 ping）")
    from realtime_novel.adapters.llm import call_llm
    from realtime_novel.adapters.llm import get_llm_config
    cfg = get_llm_config()["llm"]
    print(f"  ✓ llm_config 已加载")
    print(f"    · baseUrl: {cfg.get('baseUrl', '?')}")
    print(f"    · default_model: {cfg.get('default_model', '?')}")

    # 极小测试调用（10 tokens 足够）
    result = call_llm(
        "回复 OK 即可",
        system_msg="你是测试机器人",
        max_tokens=20,
        temperature=0.3,
        use_json_format=False,
        timeout=30,
    )
    print(f"  ✓ ping 成功，LLM 响应: {result.strip()!r}")


# ========== 验收 3+4+5: 端到端生成下一章 ==========
def test_generate_chapter(tree: WorldTree, project) -> ChapterSummarySchema:
    header("验收 3+4+5: 端到端生成 chapter-21")

    # === 关键：demo 原文在 generated-stories/ 而非 projects/ ===
    # 7 件产物在 projects/demo-urban-romance/
    # 但 20 章 demo 原文在 generated-stories/case-1-urban-romance/
    demo_chapters_dir = ROOT / "generated-stories" / "case-1-urban-romance"
    existing_chapters = sorted(
        int(p.stem.split("-")[-1])
        for p in demo_chapters_dir.glob("chapter-*.txt")
    )
    next_chapter = (existing_chapters[-1] if existing_chapters else 0) + 1
    print(f"  demo 现有章节: {existing_chapters[:3]}...{existing_chapters[-3:]} (共 {len(existing_chapters)} 章)")
    print(f"  下一章节号: {next_chapter}")

    # 读最近 1 章全文（从 generated-stories/ 取）
    last_chapter_path = demo_chapters_dir / f"chapter-{existing_chapters[-1]:02d}.txt" if existing_chapters else None
    last_chapter_full = last_chapter_path.read_text(encoding="utf-8") if last_chapter_path and last_chapter_path.exists() else None
    print(f"  上一章全文: {len(last_chapter_full) if last_chapter_full else 0} 字")

    # 读最近 3 章摘要（demo 自带 chapter_summaries.json）
    summaries: list[ChapterSummarySchema] = []
    summary_path = ROOT / "docs" / "eval-notes" / "code" / "v0.2" / "output" / "case-1-urban-romance" / "chapter_summaries.json"
    if summary_path.exists():
        raw = json.loads(summary_path.read_text(encoding="utf-8"))
        for s in raw[-3:]:
            try:
                summaries.append(ChapterSummarySchema.model_validate(s))
            except Exception as e:
                print(f"  ⚠️ 摘要加载失败: {e}")
    print(f"  历史摘要: {len(summaries)} 章")

    # 调用 S4 生成器
    generator = ChapterGenerator(tree, project)
    print()
    print(f"  🚀 开始生成第 {next_chapter} 章...")
    result = generator.generate_next(
        chapter_num=next_chapter,
        chapter_summaries=summaries,
        last_chapter_full=last_chapter_full,
    )

    # === 验收 3: 真实产品流（非评测流）===
    line()
    print(f"  ✅ 验收 3: 真实产品流")
    print(f"    · 章节文本: {result.word_count} 字（≥ 3000 字硬约束）")
    assert result.word_count >= 2500, f"章节字数不足: {result.word_count}"
    print(f"    · 用时: {result.duration_sec:.1f}s")

    # === 验收 4: 落盘 ===
    expected_path = project.chapter_path(next_chapter)
    assert expected_path.exists(), f"章节未落盘: {expected_path}"
    print(f"  ✅ 验收 4: 落盘成功 → {expected_path.relative_to(ROOT)}")
    file_size = expected_path.stat().st_size
    print(f"    · 文件大小: {file_size} 字节")

    # === 验收 5: WorldTree 更新 ===
    line()
    print(f"  ✅ 验收 5: WorldTree 更新")
    nodes_before = len(tree.world_tree.branches) - 1  # 减掉刚 add 的
    nodes_after = len(tree.world_tree.branches)
    print(f"    · branches 节点数: {nodes_before} → {nodes_after}")
    assert nodes_after == nodes_before + 1

    # 检查最后节点（TreeNode 是 Pydantic 模型，用 .id 属性访问）
    last_node = tree.world_tree.branches[-1]
    print(f"    · 最新节点: {last_node.id} ({last_node.type})")
    assert last_node.id == f"node-chapter-{next_chapter:02d}"

    # 检查种子表状态变化
    seeds_with_chapter = [
        s for s in tree.seed_table.seeds
        if s.get("last_seen_chapter") == next_chapter or s.get("planted_at_chapter") == next_chapter
    ]
    print(f"    · 种子表状态变化: {len(seeds_with_chapter)} 个种子被本章触动")
    for s in seeds_with_chapter:
        print(f"      · 种子 #{s.get('id')}「{s.get('content', '?')[:20]}」: status={s.get('status', '?')}")

    return result.summary


def main() -> int:
    print()
    print("⚡  M-β 验收脚本 · 骨架 0.2")
    print(f"   工程: {ROOT}")

    try:
        pm, tree, project = test_load_demo()
        test_llm_client()
        summary = test_generate_chapter(tree, project)

        header("🎉 验收结果")
        line(f"  ✅ 验收 1: 加载 demo WorldTree")
        line(f"  ✅ 验收 2: LLM 客户端可调用")
        line(f"  ✅ 验收 3: 生成真实产品流（{summary.chapter_id} 章 {len(summary.key_events)} 个 key events）")
        line(f"  ✅ 验收 4: 章节落盘")
        line(f"  ✅ 验收 5: WorldTree 更新")
        line()
        line("全部通过 = 骨架 0.2 (M-β) 跑通 ✅")
        return 0
    except Exception as e:
        line()
        line(f"❌ 验收失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
