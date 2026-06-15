"""
real_llm.py - v0.2 真 LLM 调用封装

复用 lunaris 的 llm_config.py (macOS SSL 绕过 + OpenAI 兼容协议)
不复制代码, 走 sys.path 引用, 配置共享 lunaris 的 config.private.json
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional


# === 复用 lunaris 的 llm_config ===
# 路径优先取 LUNARIS_ROOT 环境变量（git 拉回家后设置）
# 兑底取本机默认 /Users/wuyu/AiTest/lunaris
LUNARIS_ROOT = os.environ.get("LUNARIS_ROOT", "/Users/wuyu/AiTest/lunaris")
sys.path.insert(0, os.path.join(LUNARIS_ROOT, "backend"))


def call_llm_generate(
    prompt: str,
    *,
    system_msg: Optional[str] = None,
    use_json_format: bool = False,
    max_tokens: int = 6144,  # ~3000 字章节 + 余量
    temperature: float = 0.7,  # 创作需要一定随机性
    timeout: int = 180,
    model: Optional[str] = None,  # None = 用 lunaris config 默认
) -> str:
    """
    v0.2 章节生成专用 LLM 调用

    与 lunaris 默认的差异:
    - max_tokens: 6144（3000 字章节需要）
    - temperature: 0.7（创作需要，比 lunaris 默认 0.3 高）
    - use_json_format: 默认 False（章节是散文，不是 JSON）
    """
    from lib.llm_config import call_llm

    return call_llm(
        prompt,
        system_msg=system_msg,
        use_json_format=use_json_format,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        model=model,
    )


def call_llm_extract_summary(
    chapter_text: str,
    chapter_num: int,
    *,
    timeout: int = 60,
) -> dict:
    """
    02 §4.3 schema 提取 ChapterSummary
    强制 JSON 输出 (use_json_format=True)
    """
    from lib.llm_config import call_llm

    system_msg = """你是章节摘要提取器。严格按 JSON schema 输出，不要任何额外说明文字。
输出语言：中文。"""

    user_prompt = f"""请阅读以下第 {chapter_num} 章正文，按 JSON schema 输出摘要：

## 章节正文
{chapter_text[:5000]}

## JSON Schema
{{
  "chapter_id": {chapter_num},
  "range": "<第 N 章（段 A-B）>",
  "key_events": ["<事件 1>", "<事件 2>", "<事件 3>"],
  "seed_changes": {{
    "planted": [<新埋的种子 ID 列表>],
    "resonating": [<本章强化（再次提及）的种子 ID 列表>],
    "harvested": [<本章回收（剧情完成）的种子 ID 列表>]
  }},
  "character_state": {{ "<角色名>": "<1-2 词状态>" }},
  "unresolved": ["<存疑 1>", "<存疑 2>"]
}}

注意：
1. key_events 1-3 句
2. seed_changes 必须是整数数组，无变化则为空数组 []
3. character_state 用 1-2 个短词概括当前状态
4. unresolved 列出本章未解决的悬念"""

    raw = call_llm(
        user_prompt,
        system_msg=system_msg,
        use_json_format=True,
        max_tokens=2048,
        temperature=0.0,  # 提取任务要确定性
        timeout=timeout,
    )

    # 解析 JSON（lunaris 强制 json_object 格式，正常不会出意外）
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON 解析失败: {e}")
        print(f"   raw 前 200: {raw[:200]}")
        # 降级：返回空 schema
        return {
            "chapter_id": chapter_num,
            "range": f"第 {chapter_num} 章",
            "key_events": ["[JSON 解析失败]"],
            "seed_changes": {"planted": [], "resonating": [], "harvested": []},
            "character_state": {},
            "unresolved": [],
        }


if __name__ == "__main__":
    # 自测
    print("=== LLM 生成测试 ===")
    text = call_llm_generate(
        "用 50 字描述一个雨天的杭州街道。",
        temperature=0.7,
        max_tokens=512,
    )
    print(f"生成文本 ({len(text)} 字): {text[:200]}")

    print("\n=== JSON 提取测试 ===")
    summary = call_llm_extract_summary(
        "林远在城西老小区整理父亲遗物，发现一台 1987 年的老收音机。",
        chapter_num=1,
    )
    print(f"摘要: {json.dumps(summary, ensure_ascii=False, indent=2)}")
