"""cli/main.py — 顶层 parser + 子命令路由

M-α 阶段: 4 个子命令全部 stub，0 业务逻辑（M-γ 充实）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


# === 帮助文本 ===

HELP_DESCRIPTION = """
realtime-novel · 实时生成 + 可干预小说产品

工具链:
  - core/      核心数据模型（7 件 Schema + WorldTree + ProjectManager）
  - services/  业务服务（S4 ChapterGenerator）
  - adapters/  外部依赖（LLM 客户端 / Prompt / IO）
  - cli/       命令行入口（本文件）
  - utils/     工具类

子命令:
  new        新建项目（5 步启动链路 — M-γ 阶段实装）
  load       加载并显示项目信息
  generate   生成下一章节
  rollback   回档到指定 Node
"""


def _add_project_id_arg(parser: argparse.ArgumentParser, required: bool = True):
    """通用参数: --project-id"""
    parser.add_argument(
        "--project-id",
        required=required,
        help="项目 ID（小写 + 短横线，如 'demo-urban-romance'）",
    )


def _add_workspace_arg(parser: argparse.ArgumentParser):
    """通用参数: --workspace（默认当前目录）"""
    parser.add_argument(
        "--workspace",
        default=".",
        help="工作区根目录（默认: 当前目录）",
    )


# === 子命令实现（stub） ===

def cmd_new(args) -> int:
    """新建项目 — M-γ 阶段实装 5 步引导"""
    from realtime_novel import ProjectManager, OnboardingFlow

    workspace = Path(args.workspace).resolve()
    pm = ProjectManager(workspace_root=workspace)

    # 创建项目目录（如果不存在）
    try:
        project = pm.create(args.project_id, exist_ok=True)
    except FileExistsError as e:
        print(f"❌ {e}")
        print(f"   (用 --restart 覆盖已存在的引导状态)")
        if not getattr(args, "restart", False):
            return 1

    # 启动 5 步引导
    flow = OnboardingFlow(project)
    flow.run(force_restart=getattr(args, "restart", False))
    return 0


def cmd_load(args) -> int:
    """加载项目并显示 7 件规模"""
    from realtime_novel import ProjectManager

    pm = ProjectManager(workspace_root=Path(args.workspace).resolve())
    try:
        loaded = pm.load(args.project_id, strict=True)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1
    except Exception as e:
        print(f"❌ 加载失败: {e}")
        return 1

    print(f"📦 项目: {args.project_id}")
    print(f"   目录: {loaded.project.project_dir}")
    print()
    print(f"   7 件产物:")
    for filename, schema in loaded.artifacts.items():
        print(f"   · {filename}: {type(schema).__name__}")
    return 0


def cmd_generate(args) -> int:
    """生成下一章节 — M-β 阶段实装"""
    from realtime_novel import (
        ProjectManager,
        WorldTree,
        ChapterGenerator,
    )
    from realtime_novel.core.schemas import ChapterSummarySchema
    import json

    workspace = Path(args.workspace).resolve()
    pm = ProjectManager(workspace_root=workspace)

    try:
        loaded = pm.load(args.project_id, strict=True)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1

    project = loaded.project
    tree = WorldTree.from_dict(loaded.artifacts)

    # 找下一章节号（从 demo 项目目录取最近一章）
    demo_chapters = sorted(
        int(p.stem.split("-")[-1])
        for p in (workspace / "projects" / args.project_id / "chapters").glob("chapter-*.txt")
    )
    if not demo_chapters:
        print(f"❌ 没找到 projects/{args.project_id}/chapters/ 下的 demo 章节")
        return 1

    next_chapter = demo_chapters[-1] + 1
    last_chapter_full = (workspace / "projects" / args.project_id / "chapters" / f"chapter-{demo_chapters[-1]:02d}.txt").read_text(encoding="utf-8")

    # 读最近 3 章摘要（v0.2 输出）
    summaries = []
    summary_path = workspace / "docs" / "eval-notes" / "code" / "v0.2" / "output" / "case-1-urban-romance" / "chapter_summaries.json"
    if summary_path.exists():
        raw = json.loads(summary_path.read_text(encoding="utf-8"))
        for s in raw[-3:]:
            try:
                summaries.append(ChapterSummarySchema.model_validate(s))
            except Exception:
                pass

    print(f"🚀 生成第 {next_chapter} 章 ...")
    generator = ChapterGenerator(tree, project)
    try:
        result = generator.generate_next(
            chapter_num=next_chapter,
            chapter_summaries=summaries,
            last_chapter_full=last_chapter_full,
        )
    except Exception as e:
        print(f"❌ 生成失败: {e}")
        return 1

    print(f"   ✓ {result.word_count} 字, {result.duration_sec:.1f}s")
    print(f"   ✓ 落盘: {project.chapter_path(next_chapter).relative_to(workspace)}")
    return 0


def cmd_rollback(args) -> int:
    """回档到指定 Node — M-δ 阶段实装"""
    from realtime_novel import ProjectManager, WorldTree

    workspace = Path(args.workspace).resolve()
    pm = ProjectManager(workspace_root=workspace)

    try:
        loaded = pm.load(args.project_id, strict=True)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1

    tree = WorldTree.from_dict(loaded.artifacts)
    before = len(tree.world_tree.branches)

    try:
        deleted = tree.rollback_to(args.node_id)
    except ValueError as e:
        print(f"❌ {e}")
        return 1

    after = len(tree.world_tree.branches)
    print(f"⏪ rollback '{args.project_id}' → {args.node_id}")
    print(f"   删 {deleted} 节点: {before} → {after}")
    print(f"   ⚠️  M-α 阶段是内存操作，未落盘（M-δ 阶段实装硬 reset）")
    return 0


# === 顶层 parser ===

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m realtime_novel",
        description=HELP_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        title="子命令",
        required=True,
    )

    # new
    p = subparsers.add_parser("new", help="新建项目（5 步启动链路）")
    _add_project_id_arg(p)
    _add_workspace_arg(p)
    p.add_argument(
        "--restart",
        action="store_true",
        help="强制从头开始（清空已有引导状态）",
    )
    p.set_defaults(func=cmd_new)

    # load
    p = subparsers.add_parser("load", help="加载并显示项目信息")
    _add_project_id_arg(p)
    _add_workspace_arg(p)
    p.set_defaults(func=cmd_load)

    # generate
    p = subparsers.add_parser("generate", help="生成下一章节（M-β 实装）")
    _add_project_id_arg(p)
    _add_workspace_arg(p)
    p.set_defaults(func=cmd_generate)

    # rollback
    p = subparsers.add_parser("rollback", help="回档到指定 Node")
    _add_project_id_arg(p)
    _add_workspace_arg(p)
    p.add_argument("--node-id", required=True, help="回档目标 Node ID")
    p.set_defaults(func=cmd_rollback)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
