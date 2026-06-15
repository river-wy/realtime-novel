"""M-γ 验收脚本 — 跑通 4 项验收标准

验收标准（docs/roadmap/v0.3-product-skeleton.md §4 M-γ）:
- [ ] `python3 -m realtime_novel new` 创建新项目目录
- [ ] 5 步交互式输入完成 7 件 YAML
- [ ] 引导结束后自动生成第 1 章
- [ ] 整个流程可中断 / 恢复

策略: 验收时不真跑 5 步交互（需人工输入），改用代码直接构造 OnboardingState,
      然后调内部方法生成 7 件 + 第 1 章。

用法:
    cd /Users/wuyu/creativeToys/realtime-novel
    source .venv/bin/activate
    python tests/m3/test_onboarding.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from realtime_novel import (
    ProjectManager,
    OnboardingFlow,
    OnboardingState,
)


ROOT = Path(__file__).resolve().parents[2]


def line(s: str = "") -> None:
    print(s, flush=True)


def header(s: str) -> None:
    line()
    line("=" * 70)
    line(f"  {s}")
    line("=" * 70)


# ========== 验收 1: 创建新项目目录 ==========
# 全程持有 tmp 目录句柄，防止 with 块退出后 tmp 被清
_TMP_DIR_HOLDER: list = []


def test_create_project() -> ProjectManager:
    header("验收 1: ProjectManager.create('test-onboarding')")
    tmp = tempfile.mkdtemp(prefix="realtime_novel_m3_")
    _TMP_DIR_HOLDER.append(tmp)  # 持有引用

    pm = ProjectManager(workspace_root=tmp)
    project = pm.create("test-onboarding")
    assert project.project_dir.exists()
    assert (project.project_dir / "chapters").exists()
    # 7 件空 YAML
    yaml_files = sorted(project.project_dir.glob("*.yaml"))
    assert len(yaml_files) == 7, f"期望 7 件 YAML，实际 {len(yaml_files)}"
    print(f"  ✓ 创建项目: {project.project_dir}")
    print(f"  · chapters/ 已建")
    print(f"  · 7 件空 YAML 已落盘")
    print(f"  · tmp 目录: {tmp} (全程持有)")
    return pm


# ========== 验收 2 + 3: 7 件 YAML + 第 1 章 ==========
def test_7_artifacts_and_chapter_1(pm: ProjectManager) -> OnboardingState:
    header("验收 2+3: 5 步状态 → 7 件 YAML + 第 1 章")

    project = pm.create("test-onboarding", exist_ok=True)  # 拿 Project 对象，不是 Path
    state = OnboardingState(
        project_id="test-onboarding",
        genres=["都市"],
        styles=["言情", "治愈"],
        tone="温暖",
        palette=[],
        core_relationship="夫妻",
        emotional_anchor="想看被压抑很久的温柔",
        taboos="不要种马 / 不要爽文套路",
        ending_preference="由系统决定",
        extra_notes="现代杭州背景",
        main_conflict="主角林远发现父亲遗物，决定追寻父亲失踪的真相",
        main_beats=[
            {"title": "第 1 章：发现遗物", "description": "林远整理父亲遗物，找到一台老式收音机"},
            {"title": "第 5 章：初遇关键人物", "description": "在旧货市场遇到父亲老友"},
            {"title": "第 10 章：真相初露", "description": "从收音机中听到父亲当年的录音"},
            {"title": "第 15 章：主线推进", "description": "线索指向杭州某老地址"},
            {"title": "第 20 章：阶段高潮", "description": "抵达老地址，发现关键物证"},
        ],
        sub_plots=["林远与妻子的关系在追寻中变得紧张"],
        characters=[
            {"id": "char-001", "name": "林远", "role": "protagonist",
             "background": "28 岁杭州程序员，妻子是高中语文老师"},
            {"id": "char-002", "name": "陈岚", "role": "supporting",
             "background": "27 岁高中语文老师，林远妻子"},
            {"id": "char-003", "name": "周叔", "role": "supporting",
             "background": "林远父亲的老友，旧货市场摊主"},
        ],
        seeds=[
            {"id": 1, "content": "1987 年的收音机"},
            {"id": 2, "content": "父亲写给母亲的信"},
            {"id": 3, "content": "城西老小区的钥匙"},
        ],
    )
    flow = OnboardingFlow.__new__(OnboardingFlow)  # 绕过 __init__
    flow.project = project
    flow.state = state

    print(f"  🚀 调用 _generate_7_artifacts (会跑真 LLM 7 次, ~30s) ...")
    flow._generate_7_artifacts()
    state.artifacts_generated = True
    print(f"  ✓ 7 件 YAML 已落盘 + Pydantic 校验通过")

    line()
    print(f"  📋 7 件产物状态:")
    for filename in [
        "01-world-tree.yaml", "02-style-charter.yaml", "03-genre-resonance.yaml",
        "04-main-plot.yaml", "05-sub-plot.yaml", "06-character-card.yaml",
        "07-seed-table.yaml",
    ]:
        fpath = project.file_path(filename)
        if fpath.exists():
            size = fpath.stat().st_size
            print(f"     · {filename} ({size} 字节)")

    print()
    print(f"  🚀 调用 _generate_chapter_1 (会跑真 LLM, ~60s) ...")
    flow._generate_chapter_1()
    state.chapter_1_generated = True
    state.current_step = 5
    flow._save_state()  # 手动保存（脚本用 __new__ 绕过 __init__，需显式调）
    print(f"  ✓ 第 1 章已生成: {flow.state.chapter_1_path}")

    # 校验章节字数
    ch1 = project.chapter_path(1)
    assert ch1.exists()
    text = ch1.read_text(encoding="utf-8")
    word_count = len(text)
    print(f"  · 字数: {word_count}")
    assert word_count >= 2500, f"第 1 章字数不足: {word_count}"

    return state


# ========== 验收 4: 状态持久化（可中断 / 恢复）==========
def test_state_persistence(pm: ProjectManager) -> None:
    header("验收 4: 状态持久化（可中断 / 恢复）")

    project = pm.create("test-onboarding", exist_ok=True)  # Project 对象
    state_path = project.project_dir / OnboardingFlow.STATE_FILE
    assert state_path.exists(), f"状态文件未创建: {state_path}"
    print(f"  ✓ 状态文件: {state_path}")

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["project_id"] == "test-onboarding"
    assert data["artifacts_generated"] is True
    assert data["chapter_1_generated"] is True
    assert data["current_step"] == 5
    print(f"  · current_step: {data['current_step']}")
    print(f"  · artifacts_generated: {data['artifacts_generated']}")
    print(f"  · chapter_1_generated: {data['chapter_1_generated']}")
    print(f"  ✓ 状态正确持久化")

    # 重新加载 OnboardingFlow 验证可恢复
    flow2 = OnboardingFlow(project)
    assert flow2.state.chapter_1_generated is True
    print(f"  ✓ 重新加载 OnboardingFlow 状态一致")


def main() -> int:
    print()
    print("🪄  M-γ 验收脚本 · 骨架 0.3")
    print(f"   工程: {ROOT}")

    try:
        pm = test_create_project()
        state = test_7_artifacts_and_chapter_1(pm)
        test_state_persistence(pm)

        header("🎉 验收结果")
        line(f"  ✅ 验收 1: 创建新项目目录")
        line(f"  ✅ 验收 2: 5 步状态 → 7 件 YAML (Pydantic 校验通过)")
        line(f"  ✅ 验收 3: 自动生成第 1 章 (≥ 2500 字)")
        line(f"  ✅ 验收 4: 状态持久化（可中断/恢复）")
        line()
        line("全部通过 = 骨架 0.3 (M-γ) 跑通 ✅")
        return 0
    except Exception as e:
        line()
        line(f"❌ 验收失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
