"""OnboardingAgent — 管家 Agent 引导式多轮对话 (Step 3 + Step 4)

m-v0.5-onboarding s1.2 实现

负责:
- 接收 user_message + context=onboarding_step_N
- 读 state_json (Step 1 已存 genres/styles/tone + Step 2 palette)
- 调 LLM 生成 4 字段建议
- 推 onboarding_proposal 事件给前端
- 多轮对话: 用户修改建议 → Agent 改字段 → 推 proposal
- 用户确认 → 调 edit_artifact 写 7 件 → 推 onboarding_confirmed

设计原则:
- 每次 consult 都重新拼 messages (无状态, 拍板 3.2)
- 用 ChapterGeneratorSpecialist W2 类似的 LLM 调用方式
- LLM 4 字段输入/输出严格用 Pydantic schema 校验
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from realtime_novel.adapters.llm_adapter import get_llm_adapter
from realtime_novel.adapters.types import ModelRole
from realtime_novel.agent.prompts import (
    ONBOARDING_STEP3_PROMPT, ONBOARDING_STEP4_PROMPT,
)


# ============ Pydantic schema (LLM 输出严格) ============

class Step3Fields(BaseModel):
    """Step 3 核心设定 4 字段"""
    core_relationship: str = Field(default="", description="核心关系 (Step 3 必填)")
    emotional_anchor: str = Field(default="", description="情感锚点 (Step 3 必填)")
    taboos: str = Field(default="", description="禁区 (可空)")
    ending_preference: str = Field(default="", description="结局偏好 (可空)")


class Step4Fields(BaseModel):
    """Step 4 大纲初稿 4 字段"""
    main_conflict: str = Field(default="", description="主线核心矛盾")
    sub_plots: str = Field(default="", description="支线 (每行 1 个)")
    characters: str = Field(default="", description="人物 (每行 '名字-身份-背景')")
    seeds: str = Field(default="", description="种子 (每行 1 个)")


# ============ 提示词模板 ============
# prompts.py 加 2 个, 但也在这里定义 inline (避免 import 循环)
_STEP3_SYSTEM_FALLBACK = """你是「小说创作引导师」。

【任务】
基于用户已有的世界树基调 (genre/styles/tone) 和 palette, 为 Step 3 提议 4 个核心设定字段:
- core_relationship: 核心关系 (必填, 一句话)
- emotional_anchor: 情感锚点 (必填, 关键词列表, 如 '孤独/寻找/不信任')
- taboos: 禁区 (可空, 一句话)
- ending_preference: 结局偏好 (可空, 'HE' / 'BE' / '开放式' 等)

【输出格式】(严格 JSON)
{
  "core_relationship": "...",
  "emotional_anchor": "...",
  "taboos": "...",
  "ending_preference": "..."
}
"""

_STEP4_SYSTEM_FALLBACK = """你是「小说创作引导师」。

【任务】
基于用户已有的世界树基调 (genre/styles/tone) + Step 3 核心设定, 为 Step 4 提议 4 个大纲字段:
- main_conflict: 主线核心矛盾 (一句话)
- sub_plots: 支线 (每行 1 个, 用 \\\\n 分隔)
- characters: 人物 (每行 '名字-身份-背景' 格式, 主角放第 1 行)
- seeds: 种子 (每行 1 个, 伏笔/小巧思/角色关系碎片)

【输出格式】(严格 JSON)
{
  "main_conflict": "...",
  "sub_plots": "支线1\\\\n支线2\\\\n支线3",
  "characters": "林远-主角-28岁杭州程序员\\\\n林雪-妹妹-高中语文老师",
  "seeds": "1987年的收音机\\\\n永远没响的家里的电话"
}
"""


# ============ OnboardingAgent 主类 ============

class OnboardingAgent:
    """Step 3 + Step 4 引导式多轮对话 Agent

    每次 consult 是 stateless: 重新拼 messages, 不存 session
    """
    name = "onboarding_agent"

    async def consult(
        self,
        project_id: str,
        step: int,  # 3 or 4
        user_message: str,
        current_fields: Dict[str, str],  # 当前已有的 4 字段
    ) -> Dict[str, Any]:
        """调 LLM 生成 4 字段建议 (或修改)

        Args:
            project_id: 项目 ID
            step: 3 or 4
            user_message: 用户输入 (可空, 例如 "改一下情感锚点")
            current_fields: 当前已有的 4 字段 (修改场景用)

        Returns:
            {
                "fields": Step3Fields | Step4Fields,
                "explanation": str,  # LLM 解释为什么这样提议
            }
        """
        # 1. 读 state_json 拿 Step 1 + Step 2 已有数据
        with _get_store().connection() as conn:
            row = conn.execute(
                "SELECT state_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if not row:
            return {"fields": {}, "error": "onboarding state not found"}
        full_state = json.loads(row["state_json"])
        p = full_state.get("payload", {})

        # 2. 拼 messages
        sys_prompt = self._get_system_prompt(step, p, current_fields)

        # 3. 调 LLM
        adapter = get_llm_adapter()
        from realtime_novel.adapters.types import LLMRequest
        request = LLMRequest(
            prompt="",
            messages=[{"role": "user", "content": user_message or "请提议 4 字段"}],
            system_prompt=sys_prompt,
            max_tokens=1500,
            temperature=0.7,
            response_format={"type": "json_object"},
            role=ModelRole.TEXT,
        )
        try:
            response = await adapter.complete(request)
            raw = response.content
        except Exception as e:
            return {"fields": current_fields, "error": f"LLM 调用失败: {e}"}

        # 4. 解析 + Pydantic 校验
        try:
            data = json.loads(raw)
            if step == 3:
                fields_obj = Step3Fields.model_validate(data)
            else:
                fields_obj = Step4Fields.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            return {"fields": current_fields, "error": f"LLM 输出解析失败: {e}", "raw": raw}

        return {
            "fields": fields_obj.model_dump(),
            "raw": raw,
        }

    def _get_system_prompt(self, step: int, p: dict, current_fields: Dict[str, str]) -> str:
        """拼 system prompt: 用户已有输入 + 当前字段 + LLM 提议"""
        # 用 prompts.py 里的模板 (如果定义了), 否则 fallback
        if step == 3:
            template = ONBOARDING_STEP3_PROMPT if "ONBOARDING_STEP3_PROMPT" in globals() else _STEP3_SYSTEM_FALLBACK
        else:
            template = ONBOARDING_STEP4_PROMPT if "ONBOARDING_STEP4_PROMPT" in globals() else _STEP4_SYSTEM_FALLBACK

        # 拼上下文
        context = {
            "genres": p.get("genres", []),
            "styles": p.get("styles", []),
            "tone": p.get("tone", []),
            "palette": p.get("palette", []),
            "current_fields": current_fields,
        }

        # 模板占位符填充 (如果有)
        if "{context}" in template or "{current_fields}" in template:
            try:
                return template.format(
                    genres=", ".join(context["genres"]) or "(未选)",
                    styles=", ".join(context["styles"]) or "(未选)",
                    tone=", ".join(context["tone"]) or "(未选)",
                    palette=", ".join(context["palette"]) or "(未选)",
                    current_fields="\n".join([f"- {k}: {v}" for k, v in current_fields.items() if v]),
                )
            except KeyError:
                pass

        return template.format(**context) if "{context}" in template else template


# ============ Helper ============
def _get_store():
    """延迟 import 避免循环"""
    from realtime_novel.persistence import get_store
    return get_store()
