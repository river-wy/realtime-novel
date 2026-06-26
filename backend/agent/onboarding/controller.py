"""onboarding_controller — Onboarding Step 3/4 LLM 推演控制器

职责：
- Step 3/4 调 LLM 生成字段建议（consult 方法）
- 管家 ReAct loop 通过 onboarding_propose_step 工具调用
- 包含 JSON 解析（三层 fallback）、Pydantic 校验、重新提议检测
"""
from __future__ import annotations

import json
import re
import time
from enum import Enum
from pydantic import BaseModel, Field, ValidationError
from typing import Any, Dict, List, Optional

from backend.adapters import get_llm_adapter
from backend.adapters.types import LLMRequest, ModelRole
from backend.agent.prompts import (
    ONBOARDING_STEP3_PROMPT,
    ONBOARDING_STEP4_PROMPT,
)
from backend.agent.runtime.executor import AgentExecutor, get_agent_executor
from backend.utils.logger import logger as logger_decorator


# ============ Onboarding Step 枚举 ============

class OnboardingStep(str, Enum):
    """Onboarding 5 步"""
    STEP_1 = "step_1_world_tree"  # 题材/风格/基调（按钮）
    STEP_2 = "step_2_palette"      # palette（按钮）
    STEP_3 = "step_3_core"         # 核心设定（对话）
    STEP_4 = "step_4_outline"      # 大纲（对话）
    STEP_5 = "step_5_chapter"      # 生成第 1 章


# ============ Pydantic Schema (Step 3/4 字段校验) ============

class Step3Fields(BaseModel):
    """Step 3 字段: 故事核心设定"""
    story_core: str = Field(..., description="一句话概括故事核心冲突/悬念")
    characters: str = Field(..., description="主角 + 对手 + 盟友的关键设定")
    opening_scene: str = Field(..., description="开篇场景的一句话描述")


class Step4Fields(BaseModel):
    """Step 4 字段: 主线大纲"""
    main_arc: str = Field(..., description="主线节点（多行，每行一个节点）")
    sub_plots: str = Field(default="", description="支线故事")
    seeds: str = Field(default="", description="伏笔/钩子")


# ============ Onboarding 状态 ============

class OnboardingState(BaseModel):
    """Onboarding 流程状态 (Step 3-4 推演用)"""
    project_id: Optional[str] = None
    current_step: OnboardingStep = OnboardingStep.STEP_3
    history: List[dict] = Field(default_factory=list)
    completed: bool = False


class OnboardingResult(BaseModel):
    """Step 3-4 单轮推演结果"""
    new_state: OnboardingState
    assistant_response: str = ""
    should_generate_chapter: bool = False
    fields: Optional[Dict[str, str]] = None
    raw: Optional[str] = None
    error: Optional[str] = None


# ============ 系统提示（Step 3-4 多轮对话） ============

ONBOARDING_SYSTEM_PROMPT = """你是「小说管家」的 Onboarding 子模块。

【职责】
当用户想创建新小说时，你负责 5 步引导：
- Step 1: 引导用户选择题材/风格/基调（已通过按钮完成）
- Step 2: 引导用户选 UI 主题色（palette，已通过按钮完成）
- Step 3: 引导用户输出故事核心设定（角色/冲突/开局）
- Step 4: 引导用户输出主线大纲 + 支线 + 种子
- Step 5: 调 generate_chapter 生成第 1 章（自动触发）

【当前状态】
- Step 1-2 已通过前端按钮完成（题材/风格/基调 + palette 已落入 projects 表）
- 你只负责 Step 3-4 的多轮对话引导

【典型工作流】
1. 主动追问用户：「说说主角是谁？他/她要面对什么冲突？」
2. 用户回答后，回复确认 + 追问下一个细节
3. 多次对话后，覆盖以下字段：
   - 主角设定（性格/目标/困境）
   - 主要角色（主角 + 对手 + 盟友）
   - 故事核心冲突
   - 开篇场景
4. 主动建议大纲方向（main_arc 3-5 个节点）
5. 用户说「差不多了」「开始生成」→ 输出一段总结 + 等待管家切到 Step 5

【输出格式】
每次回复是一段对话文本（不是 JSON）。告诉用户：
- 你听到了什么（确认）
- 下一步要问什么
- 或者「设定完成，是否开始生成第 1 章？」

【约束】
- 不要急着一次问完所有问题（拆成多轮）
- 不要替用户决定情节走向（只引导）
- 用户的回答可能很短，要耐心追问
- 出现「差不多了」「开始生成」等触发词 → 在回复中说「设定完成，是否开始生成？」
"""


# ============ 重新提议检测（关键词） ============

_REGENERATE_KEYWORDS = [
    "重新提议", "重新生成", "再想想", "再想一下",
    "不一样", "为什么没变", "换个", "重做", "再来",
    "不同的", "另外的", "其他方案", "再给",
]


@logger_decorator
def _is_regenerate_request(user_message: str) -> bool:
    """检测「重新提议」信号

    匹配: 重新提议/重新生成/再想想/不一样/为什么没变/换个/重做/再来
    不匹配: 明确修改意见 (e.g. "主角改成女性")
    """
    if not user_message:
        return False
    msg = user_message.lower()
    is_regen = any(kw in msg for kw in _REGENERATE_KEYWORDS)
    if is_regen:
        _is_regenerate_request.log.info("_is_regenerate_request: 检测到重新提议信号: user_message_len=%d", len(user_message))
    return is_regen


# ============ JSON 解析（三层 fallback + 清洗） ============

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
    # 2) stack-based
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
        if c == "\\":
            escape = True
            continue
        if c == '"' and not escape:
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
    # 3) fallback
    last = text.rfind("}")
    if last != -1 and last > first:
        return text[first:last + 1]
    return text


def _sanitize_json_string(text: str) -> str:
    """清洗 JSON 字符串中 LLM 写入的裸控制字符（换行/tab 等）。

    LLM 有时在 JSON 字段值内直接写真实换行（\\n）而不是转义 \\\\n，
    导致 json.loads 报 Invalid control character。
    """
    result = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            result.append(ch)
            continue
        if ch == "\\":
            escape = True
            result.append(ch)
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            else:
                result.append(ch)
        else:
            result.append(ch)
    return "".join(result)


# ============ OnboardingController 主类 ============

@logger_decorator
class OnboardingController:
    """Onboarding 流程控制器 (v0.6.1 完整重构)

    能力 (合并自 v0.5 OnboardingAgent + v0.6 s3.5 controller):
    - Step 3-4 LLM 推演 (consult): DB 读 + context_builder + LLM + JSON 解析 + Pydantic 校验
    - Step 5 章节生成: 委托 NovelWriter
    - 重新提议检测: 11 个关键词
    - 完整 LLM CALL/RESPONSE/PARSE 边界日志

    使用方式:
        controller = get_onboarding_controller()

        # HTTP 5 步: Step 3-4 调 consult (state 走 DB, controller 不持久)
        result = await controller.consult(
            project_id="proj-123",
            step=3,
            user_message="主角是一个黑客",
            current_fields={},
        )

        # WS 路径同样调 consult (handler 转 raw args)
        result = await controller.consult(...)
    """

    def __init__(self, executor: Optional[AgentExecutor] = None):
        self.executor = executor or get_agent_executor()

    # ---------- Step 3-4 LLM 推演（吸收 OnboardingAgent.consult 全部能力） ----------

    async def consult(
        self,
        project_id: str,
        step: int,  # 3 or 4
        user_message: str,
        current_fields: Optional[Dict[str, str]] = None,
    ) -> OnboardingResult:
        """调 LLM 生成 Step 3/4 字段建议 (或修改)

        Args:
            project_id: 项目 ID
            step: 3 or 4
            user_message: 用户输入
            current_fields: 当前已有字段（修改场景）

        Returns:
            OnboardingResult: 包含 fields / raw / error / assistant_response
        """
        # v0.6.1: 入口 log (关键多轮交互边界)
        self.log.info(
            "OnboardingController.consult START: project_id=%s, step=%d, user_msg_len=%d, current_fields_keys=%s",
            project_id, step, len(user_message or ""), list((current_fields or {}).keys()),
        )
        current_fields = current_fields or {}

        # 1. 读 onboarding_state DB 拿 Step 1+2 已有数据
        try:
            from backend.persistence import get_store
            with get_store().connection() as conn:
                row = conn.execute(
                    "SELECT state_json FROM onboarding_state WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
        except Exception as e:
            self.log.error("consult: failed to read onboarding_state: %s", str(e), exc_info=True)
            return OnboardingResult(
                new_state=OnboardingState(project_id=project_id, current_step=OnboardingStep.STEP_3 if step == 3 else OnboardingStep.STEP_4),
                error=f"读取 onboarding 状态失败: {e}",
            )

        if not row:
            return OnboardingResult(
                new_state=OnboardingState(project_id=project_id, current_step=OnboardingStep.STEP_3 if step == 3 else OnboardingStep.STEP_4),
                error="onboarding state not found",
            )

        full_state = json.loads(row["state_json"])
        p = full_state.get("payload", {})

        # 2. 拼 system prompt
        sys_prompt = self._get_system_prompt(step, p, current_fields)
        if _is_regenerate_request(user_message):
            sys_prompt += "\n\n【重要】用户表示「重新提议」, 请**重新构思**一套不同的方案, 不要直接复制上一轮提议."

        # 3. 拼 messages (用 context_builder)
        from backend.agent.context import (
            build_messages_for_onboarding_step3,
            build_messages_for_onboarding_step4,
        )
        from backend.agent.specialists.exploration import get_llm_params_for_project

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

        # 4. 调 LLM
        try:
            adapter = get_llm_adapter()
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
        except Exception as e:
            self.log.error("consult: failed to build LLM request: %s", str(e), exc_info=True)
            return OnboardingResult(
                new_state=OnboardingState(project_id=project_id, current_step=OnboardingStep.STEP_3 if step == 3 else OnboardingStep.STEP_4),
                error=f"构造 LLM 请求失败: {e}",
            )

        # LLM CALL 日志
        t_llm = time.monotonic()
        msg_count = len(messages)
        total_chars = sum(len(m.get("content", "") or "") for m in messages)
        est_tokens = int(total_chars * 0.7)
        self.log.info(
            "LLM CALL: project_id=%s, step=%d, model=%s, temp=%.2f, max_tokens=%d, freq_penalty=%.2f, msg_count=%d, est_input_tokens=%d",
            project_id, step, type(adapter).__name__,
            llm_params["temperature"], llm_params["max_tokens"],
            llm_params.get("frequency_penalty", 0.0), msg_count, est_tokens,
        )
        try:
            response = await adapter.complete(request)
            raw = response.content
            self.log.info(
                "LLM RESPONSE: project_id=%s, step=%d, raw_len=%d, raw_preview=%s, elapsed=%.2fs",
                project_id, step, len(raw or ""),
                (raw or "")[:80].replace("\n", " "), time.monotonic() - t_llm,
            )
        except Exception as e:
            self.log.error(
                "LLM EXCEPTION: project_id=%s, step=%d, error=%s, elapsed=%.2fs",
                project_id, step, str(e), time.monotonic() - t_llm, exc_info=True,
            )
            return OnboardingResult(
                new_state=OnboardingState(project_id=project_id, current_step=OnboardingStep.STEP_3 if step == 3 else OnboardingStep.STEP_4),
                fields=current_fields,
                error=f"LLM 调用失败: {e}",
            )

        # 5. 解析 + Pydantic 校验
        raw_clean = _extract_json(raw) if raw else raw
        raw_clean = _sanitize_json_string(raw_clean) if raw_clean else raw_clean
        try:
            data = json.loads(raw_clean)
            if step == 3:
                fields_obj = Step3Fields.model_validate(data)
            else:
                fields_obj = Step4Fields.model_validate(data)
            self.log.info(
                "LLM PARSE OK: project_id=%s, step=%d, fields_keys=%s, used_fallback=%s",
                project_id, step, list(fields_obj.model_dump().keys()),
                raw_clean != (raw or ""),
            )
        except (json.JSONDecodeError, ValidationError) as e:
            self.log.error(
                "LLM PARSE FAIL: project_id=%s, step=%d, error=%s, raw_preview=%s",
                project_id, step, str(e), (raw or "")[:200].replace("\n", " "),
            )
            return OnboardingResult(
                new_state=OnboardingState(project_id=project_id, current_step=OnboardingStep.STEP_3 if step == 3 else OnboardingStep.STEP_4),
                fields=current_fields,
                error=f"LLM 输出解析失败: {e}",
                raw=raw,
            )

        result = OnboardingResult(
            new_state=OnboardingState(project_id=project_id, current_step=OnboardingStep.STEP_3 if step == 3 else OnboardingStep.STEP_4),
            assistant_response=f"已为 Step {step} 生成字段: {list(fields_obj.model_dump().keys())}",
            fields=fields_obj.model_dump(),
            raw=raw,
        )
        # v0.6.1: END log (成功路径)
        self.log.info(
            "OnboardingController.consult END: project_id=%s, step=%d, fields_keys=%s, raw_len=%d",
            project_id, step, list(result.fields.keys()) if result.fields else [], len(result.raw or ""),
        )
        return result

    def _get_system_prompt(self, step: int, p: dict, current_fields: Dict[str, str]) -> str:
        """拼 system prompt: 用户已有输入 + 当前字段 + LLM 提议"""
        if step == 3:
            template = ONBOARDING_STEP3_PROMPT
        else:
            template = ONBOARDING_STEP4_PROMPT

        context = {
            "genres": p.get("genres", []),
            "styles": p.get("styles", []),
            "tone": p.get("tone", []),
            "current_fields": current_fields,
        }

        try:
            return template.format(
                genres=", ".join(context["genres"]) or "(未选)",
                styles=", ".join(context["styles"]) or "(未选)",
                tone=", ".join(context["tone"]) or "(未选)",
                current_fields="\n".join([f"- {k}: {v}" for k, v in current_fields.items() if v]),
            )
        except KeyError:
            return template


# ============ 工厂方法 ============

_controller_instance: Optional[OnboardingController] = None


def get_onboarding_controller() -> OnboardingController:
    """获取单例 OnboardingController"""
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = OnboardingController()
    return _controller_instance
