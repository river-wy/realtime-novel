"""plot_tools.py — weave_plot 工具

v0.6 重构：从 v0_4_new_tools.py 拆出
v0.4 原版是 stub（手写 3 段式 plot 模板）
v0.6 改用 LLM 真实生成 next_chapter_plan（调 ChapterGeneratorSpecialist 的 LLM 链路）
"""
from __future__ import annotations

import json

from realtime_novel.agent.tools.base import BaseTool, ToolError, register_tool
from realtime_novel.agent.tools.schemas import (
    WeavePlotInput, WeavePlotResult,
)
from realtime_novel.adapters.llm_adapter import get_llm_adapter
from realtime_novel.adapters.types import ModelRole, LLMRequest


WEAVE_PLOT_PROMPT = """你是「剧情编排师」（weave_plot）。

【任务】
根据用户给出的 plot_seed，编排下一段章节的 3 段式剧情计划：
- act_1_setup: 建立场景
- act_2_conflict: 冲突
- act_3_climax: 高潮

【plot_seed】
{plot_seed}

【输出格式】（严格按 JSON）
{{
  "seed": "...",
  "act_1_setup": "...",
  "act_2_conflict": "...",
  "act_3_climax": "...",
  "next_chapter_hooks": ["...", "..."]
}}
"""


class WeavePlotTool(BaseTool):
    """编排下一段剧情（基于 plot_seed 生成 next_chapter_plan）

    v0.6 实现：调 LLM 生成 3 段式剧情（response_format=json_object）
    """
    name = "weave_plot"
    description = "编排下一段剧情（基于 plot_seed 生成 next_chapter_plan）"
    input_schema = WeavePlotInput
    output_schema = WeavePlotResult

    async def run(
        self, input: WeavePlotInput, progress_callback=None
    ) -> WeavePlotResult:
        try:
            if progress_callback:
                await progress_callback({"step": "weaving", "percentage": 30})

            adapter = get_llm_adapter()
            request = LLMRequest(
                prompt="",
                messages=[{"role": "user", "content": f"plot_seed: {input.plot_seed}"}],
                system_prompt=WEAVE_PLOT_PROMPT.format(plot_seed=input.plot_seed),
                max_tokens=800,
                temperature=0.7,
                response_format={"type": "json_object"},
                role=ModelRole.TEXT,
            )
            response = await adapter.complete(request)
            raw = response.content

            # 解析 JSON（fallback 模板）
            try:
                plan = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                plan = {
                    "seed": input.plot_seed,
                    "act_1_setup": f"建立场景：引入 '{input.plot_seed}' 作为本章开端",
                    "act_2_conflict": f"冲突：主角面对 '{input.plot_seed}' 的挑战",
                    "act_3_climax": f"高潮：主角在 '{input.plot_seed}' 的关键时刻做出选择",
                    "next_chapter_hooks": [
                        f"延续 {input.plot_seed} 的影响",
                        "埋下新伏笔",
                    ],
                }

            if progress_callback:
                await progress_callback({"step": "done", "percentage": 100})
            return WeavePlotResult(next_chapter_plan=plan)
        except Exception as e:
            return ToolError(code="WEAVE_PLOT_FAILED", message=str(e))


register_tool(WeavePlotTool())
