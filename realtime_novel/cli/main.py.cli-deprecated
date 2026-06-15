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
    """回档到指定 Node — M-δ 阶段实装（落盘式硬 reset）"""
    from realtime_novel import ProjectManager, WorldTree, RollbackManager

    workspace = Path(args.workspace).resolve()
    pm = ProjectManager(workspace_root=workspace)

    try:
        loaded = pm.load(args.project_id, strict=True)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1

    tree = WorldTree.from_dict(loaded.artifacts)
    rm = RollbackManager(tree, loaded.project)

    # 展示现有 Node 列表 (防误选)
    print(f"⏪ rollback '{args.project_id}' → {args.node_id}")
    print()
    print("  现有 Node:")
    for nid, title in rm.list_branches():
        marker = "👉" if nid == args.node_id else "  "
        print(f"   {marker} {nid}  ({title})")
    print()

    # 强确认: 输 ROLLBACK 才执行
    if not getattr(args, "yes", False):
        print("⚠️  ⚠️  ⚠️  回档是**不可逆**操作！")
        print("⚠️  回档点之后的所有 Node 和章节会被永久删除")
        print("⚠️  被裁掉的内容不可恢复")
        print()
        confirm_text = input(f"确认回档？输入 ROLLBACK（大写）以确认: ").strip()
        if confirm_text != "ROLLBACK":
            print("❌ 未确认, 取消回档")
            return 1

    # 执行回档
    result = rm.rollback(args.node_id, confirm=True)
    print()
    print(f"✓ 回档完成 → {result.target_node_id}")
    print(f"  · 删 {result.deleted_branches_count} Node")
    print(f"  · 删 {result.deleted_chapters_count} 章节文件")
    print(f"  · 剩 {result.remaining_chapters_count} 章节")
    for w in result.warnings:
        print(f"  {w}")
    return 0


def cmd_intervene(args) -> int:
    """干预下一章生成 — M-δ 阶段实装"""
    from realtime_novel import (
        ProjectManager, WorldTree, ChapterGenerator,
        InterventionParser, InterventionMode,
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

    tree = WorldTree.from_dict(loaded.artifacts)

    # 解析干预
    parser = InterventionParser(loaded.project.project_dir)
    mode = InterventionMode(args.mode)
    intervention = parser.parse(args.text, chapter_num=args.chapter, mode=mode)
    print(f"✓ 干预解析成功")
    print(f"  · 模式: {intervention.mode}")
    print(f"  · 影响章节: {intervention.chapter_num}")
    print(f"  · 提取: {intervention.extracted_payload!r}")

    # 演示: 仅生成 system_msg, 不真调 LLM（避免 LLM 开销)
    # 真调加 --apply 参数
    if not getattr(args, "apply", False):
        print()
        print(f"  · system_msg 预览:")
        for line in intervention.system_msg.splitlines():
            print(f"    {line}")
        print()
        print(f"💡 走完整生成加 --apply （会调 LLM）")
        return 0

    # 找下一章节号
    demo_chapters = sorted(
        int(p.stem.split("-")[-1])
        for p in (workspace / "projects" / args.project_id / "chapters").glob("chapter-*.txt")
    )
    if not demo_chapters:
        print(f"❌ 没找到 projects/{args.project_id}/chapters/ 下的 demo 章节")
        return 1

    next_chapter = demo_chapters[-1] + 1
    last_chapter_full = (workspace / "projects" / args.project_id / "chapters" / f"chapter-{demo_chapters[-1]:02d}.txt").read_text(encoding="utf-8")

    # 读历史摘要
    summaries = []
    summary_path = workspace / "docs" / "eval-notes" / "code" / "v0.2" / "output" / "case-1-urban-romance" / "chapter_summaries.json"
    if summary_path.exists():
        raw = json.loads(summary_path.read_text(encoding="utf-8"))
        for s in raw[-3:]:
            try:
                summaries.append(ChapterSummarySchema.model_validate(s))
            except Exception:
                pass

    # 用干预作为 system_msg 调生成
    generator = ChapterGenerator(tree, loaded.project)
    print(f"🚀 生成第 {next_chapter} 章 (应用干预) ...")
    try:
        result = generator.generate_next(
            chapter_num=next_chapter,
            chapter_summaries=summaries,
            last_chapter_full=last_chapter_full,
            system_msg=intervention.system_msg,  # M-δ: ChapterGenerator 新增 system_msg 参数
        )
    except Exception as e:
        print(f"❌ 生成失败: {e}")
        return 1

    print(f"   ✓ {result.word_count} 字, {result.duration_sec:.1f}s")
    print(f"   ✓ 落盘: {loaded.project.chapter_path(next_chapter).relative_to(workspace)}")
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
    p = subparsers.add_parser("rollback", help="回档到指定 Node (M-δ 落盘)")
    _add_project_id_arg(p)
    _add_workspace_arg(p)
    p.add_argument("--node-id", required=True, help="回档目标 Node ID")
    p.add_argument("--yes", action="store_true", help="跳过强确认（不推荐）")
    p.set_defaults(func=cmd_rollback)

    # intervene
    p = subparsers.add_parser("intervene", help="干预下一章生成 (M-δ 落盘)")
    _add_project_id_arg(p)
    _add_workspace_arg(p)
    p.add_argument(
        "--mode",
        choices=["director", "actor"],
        default="director",
        help="干预模式: director(引导式) / actor(入戏式)",
    )
    p.add_argument(
        "--chapter",
        type=int,
        required=True,
        help="干预影响哪一章",
    )
    p.add_argument(
        "--text",
        required=True,
        help="干预文本 (前缀: '我期望'/'我希望' → director, '我' → actor)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="真调 LLM 应用干预 (默认仅解析, 不调 LLM)",
    )
    p.set_defaults(func=cmd_intervene)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
