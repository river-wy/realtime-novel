"""
main.py - v0.1 评测 pipeline 主入口

按 04 §4 pipeline：
  阶段一：单用例离线生成
  阶段二：指标计算
  输出：报告

v0.1 使用 mock LLM（不调真实 API），跑通机制本身
v0.2 才接真实 friday 代理 + 真实 LLM
"""
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from pipeline.three_layer_prompt import build_full_prompt
from pipeline.report import format_metrics_report
from metrics.calc import calc_all_metrics


# === 模拟 LLM 生成章节（v0.1 mock，v0.2 接真实 API） ===
def mock_generate_chapter(
    prompt: str,
    chapter_num: int,
    beat_info: Optional[Dict] = None,
) -> str:
    """
    v0.1 mock：返回固定长度的占位文本
    包含：当前章节号 + 一些种子关键词（模拟种子强化）
    """
    base = f"""第 {chapter_num} 章

林远坐在城西老小区的客厅里，窗外是杭州的雨。纸箱已经被拆开了，里面是父亲林建国的遗物。

他拿起那台 1987 年的收音机，型号很老，但能响。"""
    if beat_info:
        title = beat_info.get("title", "")
        base += f"\n\n本章目标：{title}。"

    # 模拟种子埋下
    if chapter_num == 1:
        base += "\n\n这台收音机是他第一次注意到。"
    elif chapter_num == 2:
        base += "\n\n他想起母亲说过的话。"
    elif chapter_num == 3:
        base += "\n\n老周在街角早餐店递给他一碗面。"

    # 凑到 ~3000 字（用占位文字）
    while len(base) < 2800:
        base += "\n\n雨还在下。林远看着窗外的灰色街道，想起一些模糊的画面。"

    return base


# === 模拟章节摘要提取（v0.1 mock，v0.2 接真实 LLM 解析 JSON） ===
def mock_extract_summary(chapter_text: str, chapter_num: int) -> Dict:
    """按 02 §4.3 schema 返回 ChapterSummary"""
    key_events = []
    if "1987" in chapter_text or "收音机" in chapter_text:
        key_events.append("1987 年的收音机首次出现")
    if "信" in chapter_text:
        key_events.append("父亲遗物中的信被发现")
    if "早餐店" in chapter_text or "老周" in chapter_text:
        key_events.append("街角早餐店场景")
    if not key_events:
        key_events.append("主角在城西老小区独处")

    seed_changes = {}
    if chapter_num == 1:
        seed_changes["planted"] = [1]  # 收音机
    elif chapter_num == 3:
        seed_changes["planted"] = [3]  # 早餐店
    if chapter_num == 5:
        seed_changes["resonating"] = [1]  # 收音机强化

    return {
        "chapter_id": chapter_num,
        "range": f"第 {chapter_num} 章（段 {chapter_num*3-2}-{chapter_num*3}）",
        "key_events": key_events,
        "seed_changes": seed_changes,
        "character_state": {"林远": "内敛/回避", "陈岚": "温和/等待"},
        "unresolved": ["父亲为何留下这台收音机", "妻是否会知道信的事"],
    }


# === 种子状态自动更新（按 02 §4.4） ===
def update_seed_table(
    seed_table: Dict,
    chapter_summaries: List[Dict],
    current_segment: int,
) -> Dict:
    """根据 chapter_summaries 更新 seed 状态"""
    updated = dict(seed_table)
    updated["seeds"] = [dict(s) for s in seed_table["seeds"]]

    for s in updated["seeds"]:
        # planted -> resonating
        if s["status"] == "planted":
            for summary in chapter_summaries:
                planted_ids = summary.get("seed_changes", {}).get("planted", [])
                resonating_ids = summary.get("seed_changes", {}).get("resonating", [])
                harvested_ids = summary.get("seed_changes", {}).get("harvested", [])

                if s["id"] in resonating_ids:
                    s["status"] = "resonating"
                    s["last_seen_segment"] = current_segment
                    s["last_seen_chapter"] = summary["chapter_id"]
                elif s["id"] in planted_ids:
                    s["planted_at_segment"] = current_segment
                    s["planted_at_chapter"] = summary["chapter_id"]
                elif s["id"] in harvested_ids:
                    s["status"] = "harvested"
                    s["last_seen_segment"] = current_segment
                    s["last_seen_chapter"] = summary["chapter_id"]

    return updated


def run_eval(case_name: str, n_chapters: int = 5) -> Dict:
    """
    跑 1 个完整用例
    04 §4 阶段一（生成） + 阶段二（指标）
    v0.1 mock：每章用固定模板生成
    """
    case_dir = Path(__file__).parent / "cases" / case_name
    start_time = time.time()

    # 加载 7 件产物
    world_tree = json.load(open(case_dir / "01-world-tree.json"))
    style_charter = json.load(open(case_dir / "02-style-charter.json"))
    genre_resonance = json.load(open(case_dir / "03-genre-resonance.json"))
    main_plot = json.load(open(case_dir / "04-main-plot.json"))
    sub_plot = json.load(open(case_dir / "05-sub-plot.json"))
    character_card = json.load(open(case_dir / "06-character-card.json"))
    seed_table = json.load(open(case_dir / "07-seed-table.json"))

    chapter_texts = []
    chapter_summaries = []
    current_segment = 0

    # 阶段一：逐章生成
    for ch in range(1, n_chapters + 1):
        # 找到当前 beat
        beat_info = None
        for beat in main_plot["beats"]:
            if beat["chapter_range"]["start"] <= ch <= beat["chapter_range"]["end"]:
                beat_info = beat
                break

        # 组装三层 prompt
        prompt = build_full_prompt(
            world_tree, style_charter, genre_resonance,
            seed_table["seeds"],
            current_segment=current_segment,
            chapter_summaries=chapter_summaries[-3:],  # 最近 3 章
            last_chapter_full=chapter_texts[-1] if chapter_texts else None,
            user_input=f"第 {ch} 章",
        )

        # v0.1 mock 生成
        chapter_text = mock_generate_chapter(prompt, ch, beat_info)
        chapter_texts.append(chapter_text)

        # v0.1 mock 摘要
        summary = mock_extract_summary(chapter_text, ch)
        chapter_summaries.append(summary)

        # 推进 segment
        current_segment += 3

    # 阶段二：更新种子表
    seed_table_updated = update_seed_table(seed_table, chapter_summaries, current_segment)

    # 阶段三：计算 5 个核心指标
    metrics = calc_all_metrics(
        world_tree, style_charter, genre_resonance,
        seed_table_updated, chapter_texts, chapter_summaries,
    )

    # 阶段四：输出报告
    duration = time.time() - start_time
    report = format_metrics_report(case_name, metrics, duration, n_chapters)

    return {
        "case_name": case_name,
        "metrics": metrics,
        "report": report,
        "chapter_texts": chapter_texts,
        "chapter_summaries": chapter_summaries,
        "seed_table_final": seed_table_updated,
    }


def main():
    case_name = "case-1-urban-romance"
    print(f"🚀 启动 v0.1 评测：{case_name}")
    print(f"   (v0.1 mock 模式，5 章)")
    print()

    result = run_eval(case_name, n_chapters=5)

    print(result["report"])

    # 落盘
    output_dir = Path(__file__).parent / "output" / case_name
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "metrics.json").write_text(
        json.dumps(result["metrics"], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    (output_dir / "report.txt").write_text(result["report"], encoding="utf-8")
    (output_dir / "chapter_summaries.json").write_text(
        json.dumps(result["chapter_summaries"], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    (output_dir / "seed_table_final.json").write_text(
        json.dumps(result["seed_table_final"], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print()
    print(f"📁 报告已落盘：{output_dir}/")
    print(f"   - report.txt（人类可读）")
    print(f"   - metrics.json（机器可读）")
    print(f"   - chapter_summaries.json")
    print(f"   - seed_table_final.json")


if __name__ == "__main__":
    main()
