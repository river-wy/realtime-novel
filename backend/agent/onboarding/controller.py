"""onboarding_controller — Onboarding 5 步流程统一控制器（v0.6.1）

v0.6.1 重构（合并原 OnboardingAgent 能力）:
- 旧 OnboardingAgent.consult() 的全部能力吸收到 controller
- HTTP 5 步端点 + WS Step 3-4 推演都用这一套 controller
- 不再有独立 OnboardingAgent 类

职责（spec.md §3.1.1）:
1. HTTP POST /api/projects/{id}/onboarding: 5 步串行
   - Step 1-2: 按钮交互（题材/风格/基调 + palette），状态由 OnboardingFlow 管
   - Step 3-4: LLM 推演（多轮对话）
   - Step 5: 调 NovelWriter 生成第 1 章
2. WS handler: handle_onboarding_request_proposal / handle_onboarding_confirm
   都通过 controller 走

对应 spec.md §3.1.1
"""
from __future__ import annotations

import json
import logging
import re
import time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ValidationError

from backend.adapters import get_llm_adapter
from backend.adapters.types import LLMRequest, ModelRole
from backend.agent.runtime.executor import AgentExecutor, get_agent_executor
from backend.agent.agents.novel_writer import get_novel_writer
from backend.agent.prompts.prompts import (
    ONBOARDING_STEP3_PROMPT,
    ONBOARDING_STEP4_PROMPT,
)
from backend.utils.logger import get_logger

log = get_logger(__name__)


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
    reader_feeling: str = Field(default="", description="读者读完的情绪基调")


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


class ChapterGenResult(BaseModel):
    """Step 5 生成结果"""
    chapter_content: str = ""
    chapter_summary: str = ""
    iterations: int = 0
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


def _is_regenerate_request(user_message: str) -> bool:
    """检测「重新提议」信号

    匹配: 重新提议/重新生成/再想想/不一样/为什么没变/换个/重做/再来
    不匹配: 明确修改意见 (e.g. "主角改成女性")
    """
    if not user_message:
        return False
    msg = user_message.lower()
    return any(kw in msg for kw in _REGENERATE_KEYWORDS)


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

        # Step 5 调 generate_chapter
        chapter = await controller.run_step_5_generate_chapter(project_id)
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
            log.error("consult: failed to read onboarding_state: %s", str(e), exc_info=True)
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
        from backend.agent.specialists.specialists import get_llm_params_for_project

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
            log.error("consult: failed to build LLM request: %s", str(e), exc_info=True)
            return OnboardingResult(
                new_state=OnboardingState(project_id=project_id, current_step=OnboardingStep.STEP_3 if step == 3 else OnboardingStep.STEP_4),
                error=f"构造 LLM 请求失败: {e}",
            )

        # LLM CALL 日志
        t_llm = time.monotonic()
        msg_count = len(messages)
        total_chars = sum(len(m.get("content", "") or "") for m in messages)
        est_tokens = int(total_chars * 0.7)
        log.info(
            "LLM CALL: project_id=%s, step=%d, model=%s, temp=%.2f, max_tokens=%d, freq_penalty=%.2f, msg_count=%d, est_input_tokens=%d",
            project_id, step, type(adapter).__name__,
            llm_params["temperature"], llm_params["max_tokens"],
            llm_params.get("frequency_penalty", 0.0), msg_count, est_tokens,
        )
        try:
            response = await adapter.complete(request)
            raw = response.content
            log.info(
                "LLM RESPONSE: project_id=%s, step=%d, raw_len=%d, raw_preview=%s, elapsed=%.2fs",
                project_id, step, len(raw or ""),
                (raw or "")[:80].replace("\n", " "), time.monotonic() - t_llm,
            )
        except Exception as e:
            log.error(
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
            log.info(
                "LLM PARSE OK: project_id=%s, step=%d, fields_keys=%s, used_fallback=%s",
                project_id, step, list(fields_obj.model_dump().keys()),
                raw_clean != (raw or ""),
            )
        except (json.JSONDecodeError, ValidationError) as e:
            log.error(
                "LLM PARSE FAIL: project_id=%s, step=%d, error=%s, raw_preview=%s",
                project_id, step, str(e), (raw or "")[:200].replace("\n", " "),
            )
            return OnboardingResult(
                new_state=OnboardingState(project_id=project_id, current_step=OnboardingStep.STEP_3 if step == 3 else OnboardingStep.STEP_4),
                fields=current_fields,
                error=f"LLM 输出解析失败: {e}",
                raw=raw,
            )

        return OnboardingResult(
            new_state=OnboardingState(project_id=project_id, current_step=OnboardingStep.STEP_3 if step == 3 else OnboardingStep.STEP_4),
            assistant_response=f"已为 Step {step} 生成字段: {list(fields_obj.model_dump().keys())}",
            fields=fields_obj.model_dump(),
            raw=raw,
        )

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

    # ---------- 旧 run_step_3_or_4（保留：state 走 controller 不走 DB） ----------

    async def run_step_3_or_4(
        self,
        user_message: str,
        state: OnboardingState,
        max_tokens: int = 2048,
        temperature: float = 0.8,
    ) -> OnboardingResult:
        """运行 Step 3 或 Step 4（多轮对话引导，state 走 controller）

        这是 v0.6 s3.5 的 state-driven 版本，主要给 novel_steward 用。
        HTTP/WS 走 consult() (DB-driven)。
        """
        messages = [
            {"role": "system", "content": ONBOARDING_SYSTEM_PROMPT},
            {"role": "system", "content": f"【当前 Step】{state.current_step.value}\n【project_id】{state.project_id or '尚未创建'}"},
        ] + state.history + [
            {"role": "user", "content": user_message},
        ]

        llm_request = LLMRequest(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            role=ModelRole.TEXT,
            enable_thinking=True,
        )

        llm_response = await self.executor.llm.complete(llm_request)
        assistant_response = llm_response.content or ""

        new_history = list(state.history) + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_response},
        ]

        new_state = OnboardingState(
            project_id=state.project_id,
            current_step=state.current_step,
            history=new_history,
            completed=state.completed,
        )

        should_generate = self._should_trigger_chapter(user_message, assistant_response)
        if should_generate:
            new_state.current_step = OnboardingStep.STEP_5

        return OnboardingResult(
            new_state=new_state,
            assistant_response=assistant_response,
            should_generate_chapter=should_generate,
        )

    # ---------- Step 5 章节生成 ----------

    async def run_step_5_generate_chapter(
        self,
        project_id: str,
        user_message: str = "生成第 1 章",
    ) -> ChapterGenResult:
        """Step 5: 调 NovelWriter 生成第 1 章"""
        writer = get_novel_writer()
        chapter_output = await writer.generate_chapter(
            project_id=project_id,
            user_message=user_message,
        )
        return ChapterGenResult(
            chapter_content=chapter_output.chapter_content,
            chapter_summary=chapter_output.chapter_summary,
            iterations=chapter_output.iterations,
            error=chapter_output.error,
        )

    def _should_trigger_chapter(self, user_message: str, assistant_response: str) -> bool:
        """判断是否触发 Step 5（用户/管家说可以开始生成了）"""
        triggers = [
            "差不多了", "够了", "开始生成", "生成", "可以了",
            "下一步", "继续生成", "OK", "ok", "好",
        ]
        combined = user_message + " " + assistant_response
        return any(t in combined for t in triggers)


# ============ 工厂方法 ============

_controller_instance: Optional[OnboardingController] = None


def get_onboarding_controller() -> OnboardingController:
    """获取单例 OnboardingController"""
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = OnboardingController()
    return _controller_instance
