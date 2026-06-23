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
import logging
from typing import Any, ClassVar, Dict

from pydantic import BaseModel, Field, ValidationError

from realtime_novel.adapters.llm_adapter import get_llm_adapter
from realtime_novel.adapters.types import ModelRole
from realtime_novel.agent.prompts import (
    ONBOARDING_STEP3_PROMPT, ONBOARDING_STEP4_PROMPT,
)
from realtime_novel.utils.logger import logger


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

@logger
class OnboardingAgent:
    """Step 3 + Step 4 引导式多轮对话 Agent

    每次 consult 是 stateless: 重新拼 messages, 不存 session
    """
    log: ClassVar[logging.Logger]  # 由 @logger 装饰器注入
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

        # v0.8.3: 检测「重新提议」信号, 调 LLM 重新构思 (不直接 copy)
        if self._is_regenerate_request(user_message):
            sys_prompt += "\n\n【重要】用户表示「重新提议」, 请**重新构思**一套不同的方案, 不要直接复制上一轮提议."

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
        # v0.8.3: LLM 调用边界日志 (model, temperature, msg_count, 预计 token)
        import time
        t_llm = time.monotonic()
        msg_count = len(messages)
        total_chars = sum(len(m.get("content", "") or "") for m in messages)
        est_tokens = int(total_chars * 0.7)  # 保守估计, 实际可能 1.5-2 字符/token
        self.log.info("LLM CALL: project_id=%s, step=%d, model=%s, temp=%.2f, max_tokens=%d, freq_penalty=%.2f, msg_count=%d, est_input_tokens=%d",
                 project_id, step, type(adapter).__name__,
                 llm_params["temperature"], llm_params["max_tokens"],
                 llm_params.get("frequency_penalty", 0.0), msg_count, est_tokens)
        try:
            response = await adapter.complete(request)
            raw = response.content
            self.log.info("LLM RESPONSE: project_id=%s, step=%d, raw_len=%d, raw_preview=%s, elapsed=%.2fs",
                     project_id, step, len(raw or ""),
                     (raw or "")[:80].replace("\n", " "), time.monotonic() - t_llm)
        except Exception as e:
            self.log.error("LLM EXCEPTION: project_id=%s, step=%d, error=%s, elapsed=%.2fs",
                      project_id, step, str(e), time.monotonic() - t_llm, exc_info=True)
            return {"fields": current_fields, "error": f"LLM 调用失败: {e}"}

        # 4. 解析 + Pydantic 校验
        # v0.8.3: LLM 偶尔返 markdown 包裹的 JSON (即使 response_format=json_object 也不一定 100% 严格)
        # 先 strip markdown code block, 再 parse
        import re
        def _extract_json(text: str) -> str:
            """从 LLM 输出中提取 JSON object. 三种策略递进:
            1) ```json ... ``` markdown 块
            2) stack-based 提取 (从首个 { 开始, 跳到平衡的 })
            3) rfind 最后一个 } 作为 fallback
            """
            # 1) markdown code block
            m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
            if m:
                return m.group(1)
            # 2) stack-based: 从首个 { 开始, 累计 { - }, 到 0 为结束
            first = text.find("{")
            if first == -1:
                return text
            depth = 0
            in_string = False
            escape = False
            for i in range(first, len(text)):
                c = text[i]
                if escape:
                    escape = False
                    continue
                if c == "\\\\":
                    escape = True
                    continue
                if c == '\"' and not escape:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return text[first:i + 1]
            # 3) fallback: rfind
            last = text.rfind("}")
            if last != -1 and last > first:
                return text[first:last + 1]
            return text

        raw_clean = _extract_json(raw) if raw else raw
        try:
            data = json.loads(raw_clean)
            if step == 3:
                fields_obj = Step3Fields.model_validate(data)
            else:
                fields_obj = Step4Fields.model_validate(data)
            self.log.info("LLM PARSE OK: project_id=%s, step=%d, fields_keys=%s, used_fallback=%s",
                     project_id, step, list(fields_obj.model_dump().keys()),
                     raw_clean != (raw or ""))
        except (json.JSONDecodeError, ValidationError) as e:
            self.log.error("LLM PARSE FAIL: project_id=%s, step=%d, error=%s, raw_preview=%s",
                      project_id, step, str(e), (raw or "")[:200].replace("\n", " "))
            return {"fields": current_fields, "error": f"LLM 输出解析失败: {e}", "raw": raw}

        return {
            "fields": fields_obj.model_dump(),
            "raw": raw,
        }

    def _is_regenerate_request(self, user_message: str) -> bool:
        """v0.8.3: 检测「重新提议」信号

        匹配: 重新提议/重新生成/再想想/不一样/为什么没变/换个/重做/再来
        不匹配: 明确修改意见 (e.g. "主角改成女性")
        """
        if not user_message:
            return False
        keywords = [
            "重新提议", "重新生成", "再想想", "再想一下",
            "不一样", "为什么没变", "换个", "重做", "再来",
            "不同的", "另外的", "其他方案", "再给",
        ]
        msg = user_message.lower()
        return any(kw in msg for kw in keywords)

    def _get_system_prompt(self, step: int, p: dict, current_fields: Dict[str, str]) -> str:
        """拼 system prompt: 用户已有输入 + 当前字段 + LLM 提议

        v0.8.2: 统一从 prompts.py 读取模板, 不再用 inline fallback
        """
        if step == 3:
            template = ONBOARDING_STEP3_PROMPT
        else:
            template = ONBOARDING_STEP4_PROMPT

        # 拼上下文 (v0.8.3: palette 不进 prompt, 仅影响 UI 主题)
        context = {
            "genres": p.get("genres", []),
            "styles": p.get("styles", []),
            "tone": p.get("tone", []),
            "current_fields": current_fields,
        }

        # 模板占位符填充
        try:
            return template.format(
                genres=", ".join(context["genres"]) or "(未选)",
                styles=", ".join(context["styles"]) or "(未选)",
                tone=", ".join(context["tone"]) or "(未选)",
                current_fields="\n".join([f"- {k}: {v}" for k, v in current_fields.items() if v]),
            )
        except KeyError:
            # 模板缺占位符时退回 raw 模板 (不阻断)
            return template


# ============ 项目名自动生成 (v0.8.3 新增) ============

GENERATE_NAME_PROMPT = """你是「小说命名师」。根据下面的故事核心, 生成 1 个项目名。

要求:
- 中文 (1-15 字, 鼓励), 也可英文
- 携带故事核心悬念/冲突的关键词
- 避免「小说/世界/世界线」等泛词
- 不用冒号/书名号
- 1 个, 不要列表

示例 (看格式不抄内容):
- 白小楼借仙界一季还雪国万灯
- 杀妻者自赎录
- The Last Letter from Mars

故事核心: {story_core}
主角/对手/盟友: {characters}
题材: {tone}

只返名字, 不要说明, 不要引号. 严格返一个 string.
"""


@logger
async def _generate_project_name(story_core: str, characters: str, tone: list[str] | str) -> str:
    """v0.8.3: Step 4 完成后 LLM 自动生成项目名

    Args:
        story_core: Step 3 故事内核
        characters: Step 3 主要角色
        tone: 题材/风格/基调 (list 或 str)
    Returns:
        生成的项目名, 失败时返 ""
    """
    from realtime_novel.adapters import get_llm_adapter
    from realtime_novel.adapters.types import LLMRequest, ModelRole
    log = _generate_project_name.log

    if isinstance(tone, str):
        tone = [tone] if tone else []
    tone_str = ", ".join(tone) or "(未选)"

    try:
        adapter = get_llm_adapter()
        request = LLMRequest(
            prompt="",
            messages=[{
                "role": "user",
                "content": GENERATE_NAME_PROMPT.format(
                    story_core=story_core[:300],
                    characters=characters[:300],
                    tone=tone_str,
                ),
            }],
            max_tokens=100,
            temperature=1.0,
            role=ModelRole.TEXT,
        )
        response = await adapter.complete(request)
        raw = (response.content or "").strip()
        # 清理: 取第一行, 去引号
        name = raw.split("\n")[0].strip().strip("'\"`'「」《》")
        # 限长 50 字
        name = name[:50]
        # 过滤: 不能是空, 不能太长
        if not name or len(name) < 2:
            log.warning("auto-name: too short, raw=%s", raw[:100])
            return ""
        log.info("auto-name generated: %s", name)
        return name
    except Exception as e:
        log.error("auto-name failed: %s", str(e))
        return ""


# ============ Helper ============
def _get_store():
    """延迟 import 避免循环"""
    from realtime_novel.persistence import get_store
    return get_store()
