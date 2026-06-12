"""
main.py - v0.2 评测 pipeline 主入口

v0.2 vs v0.1:
- 用真 LLM 替换 mock（real_llm.call_llm_generate + call_llm_extract_summary）
- 章节数从 5 扩到 20（让 overdue 能触发）
- 落盘 5 个文件（+ 章节全文）
"""
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# 让 pipeline 子模块可被导入
sys.path.insert(0, os.path.dirname(__file__))

from pipeline.three_layer_prompt import build_full_prompt
from pipeline.real_llm import call_llm_generate, call_llm_extract_summary
from pipeline.report import format_metrics_report
from metrics.calc import calc_all_metrics, update_seed_table


def run_eval(case_name: str, n_chapters: int = 20, model: Optional[str] = None) -> Dict:
    """
    跑 1 个完整用例（真 LLM）
    04 §4 阶段一（生成） + 阶段二（指标）
    """
    case_dir = Path(__file__).parent / "cases" / case_name
    start_time = time.time()

    # 加载 7 件产物
    world_tree = json.load(open(case_dir / "01-world-tree.json", encoding="utf-8"))
    style_charter = json.load(open(case_dir / "02-style-charter.json", encoding="utf-8"))
    genre_resonance = json.load(open(case_dir / "03-genre-resonance.json", encoding="utf-8"))
    main_plot = json.load(open(case_dir / "04-main-plot.json", encoding="utf-8"))
    sub_plot = json.load(open(case_dir / "05-sub-plot.json", encoding="utf-8"))
    character_card = json.load(open(case_dir / "06-character-card.json", encoding="utf-8"))
    seed_table = json.load(open(case_dir / "07-seed-table.json", encoding="utf-8"))

    chapter_texts = []
    chapter_summaries = []
    current_segment = 0

    print(f"🚀 开始生成 {n_chapters} 章...")
    print(f"   模型: deepseek-v4-pro（lunaris config 默认）")
    print(f"   temperature: 0.7")
    print(f"   max_tokens: 6144")
    print()

    for ch in range(1, n_chapters + 1):
        chapter_start = time.time()
        print(f"📝 第 {ch:>2}/{n_chapters} 章 ...", end=" ", flush=True)

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
            character_card=character_card,
            main_plot=main_plot,
            current_segment=current_segment,
            chapter_summaries=chapter_summaries[-3:],
            last_chapter_full=chapter_texts[-1] if chapter_texts else None,
            user_input=f"第 {ch} 章\n目标: {beat_info['title'] if beat_info else '推进剧情'}\n说明: {beat_info['description'] if beat_info else ''}",
        )

        # === 真 LLM 生成章节 ===
        try:
            chapter_text = call_llm_generate(
                prompt,
                temperature=0.7,
                max_tokens=6144,
                timeout=180,
                model=model,
            )
        except Exception as e:
            print(f"❌ 生成失败: {e}")
            chapter_text = f"[生成失败] {e}"

        chapter_texts.append(chapter_text)

        # === 真 LLM 提取摘要 ===
        try:
            summary = call_llm_extract_summary(chapter_text, ch, timeout=60)
        except Exception as e:
            print(f"❌ 摘要提取失败: {e}")
            summary = {
                "chapter_id": ch,
                "range": f"第 {ch} 章",
                "key_events": ["[摘要失败]"],
                "seed_changes": {"planted": [], "resonating": [], "harvested": []},
                "character_state": {},
                "unresolved": [],
            }

        chapter_summaries.append(summary)

        # 推进 segment
        current_segment += 3

        elapsed = time.time() - chapter_start
        print(f"✅ {len(chapter_text):>5} 字 | {elapsed:.1f}s")

    # 阶段二：更新种子表
    seed_table_updated = update_seed_table(seed_table, chapter_summaries, current_segment)

    # 阶段三：计算 5 个核心指标
    print()
    print("📊 计算 5 个核心指标 ...")
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
        "duration": duration,
    }


def main():
    case_name = "case-1-urban-romance"
    n_chapters = int(os.environ.get('N_CHAPTERS', '20'))
    model = os.environ.get('MODEL', None)  # None = lunaris config 默认
    print(f"🚀 启动 v0.2 评测：{case_name}")
    print(f"   章节数: {n_chapters}")
    print(f"   模型: {model or 'lunaris config 默认'}")
    print()

    result = run_eval(case_name, n_chapters=n_chapters, model=model)

    print()
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

    # v0.2 新增：保存章节全文
    chapters_dir = output_dir / "chapters"
    chapters_dir.mkdir(exist_ok=True)
    for i, text in enumerate(result["chapter_texts"], 1):
        (chapters_dir / f"chapter-{i:02d}.txt").write_text(text, encoding="utf-8")

    print()
    print(f"📁 报告已落盘：{output_dir}/")
    print(f"   - report.txt（人类可读）")
    print(f"   - metrics.json（机器可读）")
    print(f"   - chapter_summaries.json")
    print(f"   - seed_table_final.json")
    print(f"   - chapters/chapter-XX.txt（{len(result['chapter_texts'])} 章全文）")


if __name__ == "__main__":
    main()
