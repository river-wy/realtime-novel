"""OnboardingAgent — 管家 Agent 引导式多轮对话 (Step 3 + Step 4)

负责:
- 接收 user_message + context=onboarding_step_N
- 读 state_json (Step 1 已存 genres/styles/tone + Step 2 palette)
- 调 LLM 生成 4 字段建议
- 推 onboarding_proposal 事件给前端
- 多轮对话: 用户修改建议 → Agent 改字段 → 推 proposal
- 用户确认 → 调 edit_artifact 写 7 件 → 推 onboarding_confirmed

设计原则:
- 每次 consult 都重新拼 messages
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
    """Step 3 故事引擎 3 字段 """
    story_core: str = Field(default="", description="故事内核: 主角要做什么 + 什么阻止 + 如何发展")
    characters: str = Field(default="", description="主要角色: 主角/对手/盟友, 每行 '名字-身份-和主角关系'")
    opening_scene: str = Field(default="", description="开篇场景: 场景 + 主角不可逆选择")


class Step4Fields(BaseModel):
    """Step 4 故事路径 4 字段 """
    main_arc: str = Field(default="", description="主线节点: 3-5 个剧情转折, 每行 1 个")
    sub_plots: str = Field(default="", description="支线, 每行 1 个")
    seeds: str = Field(default="", description="种子/钩子, 每行 1 个")
    reader_feeling: str = Field(default="", description="读者情绪: 读者合上书那一刻心里留下什么")


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
        from realtime_novel.agent.context_builder import (
            build_messages_for_onboarding_step3,
            build_messages_for_onboarding_step4,
        )
        from realtime_novel.agent.specialists import get_llm_params_for_project
        sys_prompt = self._get_system_prompt(step, p, current_fields)

        if step == 3:
            messages = build_messages_for_onboarding_step3(
                project_id=project_id,
                current_user_message=user_message,
                system_prompt=sys_prompt,
                current_fields=current_fields,
            )
        else:
            messages = build_messages_for_onboarding_step4(
                project_id=project_id,
                current_user_message=user_message,
                system_prompt=sys_prompt,
                current_fields=current_fields,
            )

        # 3. 调 LLM
        adapter = get_llm_adapter()
        from realtime_novel.adapters.types import LLMRequest
        llm_params = get_llm_params_for_project(project_id, role="onboarding")
        request = LLMRequest(
            prompt="",
            messages=messages,
            max_tokens=llm_params["max_tokens"],
            temperature=llm_params["temperature"],
            frequency_penalty=llm_params.get("frequency_penalty", 0.0),
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
        """拼 system prompt: 用户已有输入 + 当前字段 + LLM 提议

        v0.8.2: 统一从 prompts.py 读取模板, 不再用 inline fallback
        """
        if step == 3:
            template = ONBOARDING_STEP3_PROMPT
        else:
            template = ONBOARDING_STEP4_PROMPT

        # 拼上下文
        context = {
            "genres": p.get("genres", []),
            "styles": p.get("styles", []),
            "tone": p.get("tone", []),
            "palette": p.get("palette", []),
            "current_fields": current_fields,
        }

        # 模板占位符填充
        try:
            return template.format(
                genres=", ".join(context["genres"]) or "(未选)",
                styles=", ".join(context["styles"]) or "(未选)",
                tone=", ".join(context["tone"]) or "(未选)",
                palette=", ".join(context["palette"]) or "(未选)",
                current_fields="\n".join([f"- {k}: {v}" for k, v in current_fields.items() if v]),
            )
        except KeyError:
            # 模板缺占位符时退回 raw 模板 (不阻断)
            return template


# ============ Helper ============
def _get_store():
    """延迟 import 避免循环"""
    from realtime_novel.persistence import get_store
    return get_store()
