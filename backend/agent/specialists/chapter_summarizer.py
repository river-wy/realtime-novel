"""chapter_summarizer — 章节 summary 同步抽 + 异步压缩

设计：
- 文笔家 LLM 输出格式：
    [章节正文 2000-3000 字]

    ###SUMMARY###
    1 句话剧情总结
    ###END_SUMMARY###
- 工具用 sentinel 解析（sentinel-tagged 块，robust parser）
- 解析失败 → fallback：取正文前 200 字截断 + "..."
"""
from __future__ import annotations

import re
from typing import Optional, Tuple


# Sentinel tags（文笔家 prompt 规定）
SUMMARY_START = "###SUMMARY###"
SUMMARY_END = "###END_SUMMARY###"


def extract_summary_from_llm_output(llm_output: str) -> Optional[str]:
    """从 LLM 输出里抽 1 句话 summary

    Returns:
        summary 字符串（清洗后），None 表示解析失败
    """
    if not llm_output:
        return None

    # 找 sentinel 块
    pattern = re.compile(
        re.escape(SUMMARY_START) + r"\s*\n?(.*?)\n?\s*" + re.escape(SUMMARY_END),
        re.DOTALL,
    )
    match = pattern.search(llm_output)
    if not match:
        return None

    summary = match.group(1).strip()
    # 清洗：去掉多余空白/换行
    summary = re.sub(r"\s+", " ", summary).strip()
    # 限制长度（~20-30 tokens ≈ 60-100 chars）
    if len(summary) > 200:
        summary = summary[:200] + "..."

    return summary if summary else None


def parse_chapter_summary(llm_output: str) -> Optional[str]:
    """从 LLM 输出里剥掉 sentinel 块，返回纯正文

    Returns:
        纯章节正文，None 表示解析失败
    """
    if not llm_output:
        return None

    # 找 sentinel 块
    pattern = re.compile(
        re.escape(SUMMARY_START) + r".*?" + re.escape(SUMMARY_END) + r"\s*",
        re.DOTALL,
    )
    body = pattern.sub("", llm_output).strip()
    return body if body else None


def fallback_summary(content: str, max_chars: int = 100) -> str:
    """解析失败时的 fallback：取前 N 字截断"""
    if not content:
        return ""
    # 去标题行（# 第 N 章）
    lines = content.split("\n")
    body_lines = [l for l in lines if not l.strip().startswith("# ")]
    body = " ".join(body_lines).strip()
    if len(body) > max_chars:
        return body[:max_chars] + "..."
    return body


def extract_summary_safe(llm_output: str) -> Tuple[Optional[str], Optional[str]]:
    """safe 解析：sentinel 块存在 → 抽；不存在 → fallback

    Returns:
        (summary, body) 元组，任一为 None 表示对应部分失败
    """
    summary = extract_summary_from_llm_output(llm_output)
    body = parse_chapter_summary(llm_output)
    if not summary:
        # fallback：取前 100 字
        summary = fallback_summary(llm_output, max_chars=100)
    if not body:
        body = llm_output
    return summary, body
