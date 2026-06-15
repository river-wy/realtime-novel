"""
report.py - 评测报告生成器
"""
import json
import time
from datetime import datetime
from typing import Dict, List


def format_metrics_report(
    case_name: str,
    metrics: Dict,
    duration_seconds: float,
    n_chapters: int,
) -> str:
    """生成可读评测报告"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("=" * 70)
    lines.append(f"  realtime-novel 评测报告 · v0.1")
    lines.append("=" * 70)
    lines.append(f"  用例: {case_name}")
    lines.append(f"  时间: {timestamp}")
    lines.append(f"  章节数: {n_chapters}")
    lines.append(f"  耗时: {duration_seconds:.2f}s")
    lines.append("=" * 70)
    lines.append("")

    # 指标总览
    lines.append("【5 个核心指标】")
    lines.append("")

    total = len(metrics)
    passed = sum(1 for m in metrics.values() if m.get("passed", False))

    for name, m in metrics.items():
        target = m.get("target", "?")
        target_comp = m.get("target_comparison", ">=")
        value = m.get("value", "?")
        detail = m.get("detail", "")
        passed_mark = "✅" if m.get("passed") else "❌"

        lines.append(f"  {passed_mark} {name}")
        lines.append(f"     实际值: {value}")
        lines.append(f"     目标值: {target_comp} {target}")
        lines.append(f"     详情: {detail}")
        lines.append("")

    lines.append("=" * 70)
    lines.append(f"  总览: {passed}/{total} 指标达标")
    lines.append("=" * 70)
    lines.append("")

    # 调优提示（基于未达标的指标）
    if passed < total:
        lines.append("【调优提示】")
        lines.append("")
        for name, m in metrics.items():
            if not m.get("passed"):
                lines.append(f"  ⚠️  {name} 未达标")
                if "种子回收率" in name:
                    lines.append("     → 检查 02 §2 4 维权重公式的 overdue_score 是否过低")
                    lines.append("     → 考虑调高 overdue_score 下限（默认 0.5）")
                elif "基座约束" in name:
                    lines.append("     → 检查 WorldTree.core_rules 的 hard 规则关键词字典")
                    lines.append("     → 考虑在 prompt 中强化基座层位置")
                elif "具体性颗粒" in name:
                    lines.append("     → 短章节下分母太小，密度虚高——需要章节长度 >= 2000 字再算")
                    lines.append("     → 或调整检测关键词字典（更严格）")
                elif "overdue" in name:
                    lines.append("     → 检查种子埋下时机和 planned_interval 设置")
                elif "importance" in name:
                    lines.append("     → 检查 importance 预设数值表（02 §2.4）")
                    lines.append("     → 考虑 importance=主线推进 优先于其他")
                lines.append("")
    else:
        lines.append("🎉 全部 5 个指标达标！")
        lines.append("")
        lines.append("【下一步建议】")
        lines.append("  1. 用用例 1 的指标值作为 baseline")
        lines.append("  2. 调优 02/03 schema 后重跑，对比变化")
        lines.append("  3. 写更多用例验证一致性")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    # 用 calc.py 的模拟数据
    import os
    metrics = {
        "1_种子回收率": {"value": 0.667, "target": 0.7, "passed": False, "detail": "2/3 种子被回收"},
        "2_基座约束遵守率": {"value": 1.0, "target": 1.0, "passed": True, "detail": "无违反"},
        "3_具体性颗粒密度": {"value": 25.64, "target": 3.0, "target_comparison": "<=", "passed": False, "detail": "短文本下虚高"},
        "4_overdue_触发命中率": {"value": 1.0, "target": 0.9, "passed": True, "detail": "1/1 命中"},
        "5_importance_优先采纳率": {"value": 0.5, "target": 0.8, "passed": False, "detail": "1/2 主线种子被回收"},
    }
    report = format_metrics_report("case-1-urban-romance (mock)", metrics, 1.23, 5)
    print(report)
