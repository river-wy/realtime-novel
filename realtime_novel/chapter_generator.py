"""chapter_generator.py — S4 ChapterGenerator

职责（来自 docs/roadmap/v0.3-product-skeleton.md §3 S4）:
- 输入 WorldTree + 干预
- 组装 prompt（3 层）
- 调 LLM 生成章节
- 调 LLM 提取摘要
- 落盘章节文本
- 更新 WorldTree (Node + seed 状态 + summary 链)
- 落盘 7 件 YAML

关键设计点:
- 3 层 prompt（realtime_novel.three_layer_prompt）
- 种子提取：生成后从章节文本由 LLM 抽取 key_events，反向更新 seed 状态
- 摘要滚动：每 15 章生成一次阶段摘要（M-β 简化：每章都跑全量）
- 字数校验：≥ 3000 字（design/00 §2.1）

M-α vs M-β 边界:
- M-α: 加载 demo + 实例化 WorldTree
- M-β: 生成下一章（chapter-21）真实产品流（不是 eval 流）
- M-γ: 5 步启动链路 + 完整新项目
- M-δ: 干预 + 回档 orchestrator
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict

from .world_tree import WorldTree
from .three_layer_prompt import build_full_prompt
from .llm import call_llm
from .schemas import ChapterSummarySchema
from .io import write as io_write
from .project import Project


# === 段落长度估算（v0.2 用的 3 段/章） ===
SEGMENTS_PER_CHAPTER = 3


# === 摘要提取 prompt 模板（来自 v0.2/real_llm）===
SUMMARY_PROMPT_TEMPLATE = """请阅读以下小说章节文本，提取结构化摘要。

## 章节号
第 {chapter_num} 章

## 章节文本
{chapter_text}

## 提取要求（严格按 JSON 输出）

```json
{{
  "chapter_id": {chapter_num},
  "range": "第 {chapter_num} 章",
  "key_events": ["本章发生的 2-4 个关键事件"],
  "seed_changes": {{
    "planted":   [本章新埋的种子 ID（整数列表，没有就空）],
    "resonating":[本章强化中的种子 ID],
    "harvested": [本章回收/兑现的种子 ID]
  }},
  "character_state": {{
    "人物名": "本章末尾的心理状态/处境（一句话）"
  }},
  "unresolved": ["本章留下未解决的悬念"]
}}
```

只输出 JSON，不要有任何解释。"""


@dataclass
class GenerationResult:
    """单次生成结果"""
    chapter_num: int
    chapter_text: str
    summary: ChapterSummarySchema
    duration_sec: float
    word_count: int


class ChapterGenerator:
    """S4 · 章节生成 orchestrator"""

    def __init__(
        self,
        tree: WorldTree,
        project: Project,
        *,
        temperature: float = 0.7,
        max_tokens: int = 6144,
        timeout: int = 180,
    ):
        self.tree = tree
        self.project = project
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate_next(
        self,
        chapter_num: int,
        chapter_summaries: List[ChapterSummarySchema],
        last_chapter_full: Optional[str] = None,
        user_input: Optional[str] = None,
    ) -> GenerationResult:
        """生成下一章节

        Args:
            chapter_num: 章节号（>= 1）
            chapter_summaries: 之前所有章节的摘要（按章节号顺序）
            last_chapter_full: 上一章全文（用于最近轮次层）
            user_input: 用户干预/导演输入（可选）

        Returns:
            GenerationResult 含章节文本 + 摘要 + 时长
        """
        # 1. 找当前 beat
        current_beat = self._find_current_beat(chapter_num)
        beat_info = current_beat or {}
        if user_input is None:
            user_input = f"第 {chapter_num} 章\n目标: {beat_info.get('title', '推进剧情')}\n说明: {beat_info.get('description', '')}"

        # 2. 计算 current_segment（从已有摘要反推）
        current_segment = chapter_num * SEGMENTS_PER_CHAPTER

        # 3. 组装 prompt
        prompt = build_full_prompt(
            world_tree=self.tree.world_tree,
            style_charter=self.tree.style_charter,
            genre_resonance=self.tree.genre_resonance,
            seeds=self.tree.seed_table.seeds,
            character_card=self.tree.character_card,
            main_plot=self.tree.main_plot,
            current_segment=current_segment,
            chapter_summaries=[s.model_dump() for s in chapter_summaries[-3:]],
            last_chapter_full=last_chapter_full,
            user_input=user_input,
        )

        # 4. 调 LLM 生成章节
        t0 = time.time()
        chapter_text = call_llm(
            prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            use_json_format=False,
            timeout=self.timeout,
        )
        duration = time.time() - t0

        # 5. 调 LLM 提取摘要
        summary = self._extract_summary(chapter_text, chapter_num)

        # 6. 落盘章节
        chapter_path = self.project.chapter_path(chapter_num)
        chapter_path.parent.mkdir(parents=True, exist_ok=True)
        chapter_path.write_text(chapter_text, encoding="utf-8")

        # 7. 更新 WorldTree（内存）
        self._update_worldtree(chapter_num, summary, current_segment)

        return GenerationResult(
            chapter_num=chapter_num,
            chapter_text=chapter_text,
            summary=summary,
            duration_sec=duration,
            word_count=len(chapter_text),
        )

    # === 内部方法 ===

    def _find_current_beat(self, chapter_num: int) -> Optional[dict]:
        """找当前章节对应的主线节拍（按 chapter_range）"""
        for beat in self.tree.main_plot.beats:
            r = beat.get("chapter_range", {})
            if r.get("start", 0) <= chapter_num <= r.get("end", 0):
                return beat
        return None

    def _extract_summary(self, chapter_text: str, chapter_num: int) -> ChapterSummarySchema:
        """调 LLM 提取结构化摘要"""
        summary_prompt = SUMMARY_PROMPT_TEMPLATE.format(
            chapter_num=chapter_num,
            chapter_text=chapter_text[:4000],  # 截断防超 token
        )
        try:
            raw = call_llm(
                summary_prompt,
                system_msg="你是结构化数据提取专家。严格按 JSON 输出，无任何解释。",
                temperature=0.3,
                max_tokens=1500,
                use_json_format=True,
                timeout=60,
            )
            data = json.loads(raw)
            return ChapterSummarySchema.model_validate(data)
        except Exception as e:
            # 摘要失败兜底
            return ChapterSummarySchema(
                chapter_id=chapter_num,
                range=f"第 {chapter_num} 章",
                key_events=["[摘要提取失败]"],
                unresolved=[f"摘要异常: {str(e)[:100]}"],
            )

    def _update_worldtree(
        self,
        chapter_num: int,
        summary: ChapterSummarySchema,
        current_segment: int,
    ) -> None:
        """更新 WorldTree 内存状态（不写盘 — 调用方决定是否落盘）"""
        # 添加新 Node 到 WorldTree.branches
        new_node = {
            "id": f"node-chapter-{chapter_num:02d}",
            "type": "scene",
            "title": f"第 {chapter_num} 章",
            "parent_id": None,
            "status": "completed",
            "children": [],
        }
        self.tree.add_node(new_node)

        # 更新种子表状态（按 summary.seed_changes）
        changes = summary.seed_changes
        for seed in self.tree.seed_table.seeds:
            sid = seed.get("id")
            if sid in changes.planted:
                seed["status"] = "planted"
                seed["planted_at_chapter"] = chapter_num
                seed["planted_at_segment"] = current_segment
                seed["last_seen_chapter"] = chapter_num
                seed["last_seen_segment"] = current_segment
            elif sid in changes.resonating:
                seed["status"] = "resonating"
                seed["last_seen_chapter"] = chapter_num
                seed["last_seen_segment"] = current_segment
            elif sid in changes.harvested:
                seed["status"] = "harvested"
                seed["last_seen_chapter"] = chapter_num
                seed["last_seen_segment"] = current_segment
