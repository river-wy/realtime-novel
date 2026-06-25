"""intent_recognizer — 意图识别（v0.6 小说管家的内部组件）

职责：
- 接收用户消息 + 上下文（是否有 projectId / 是否在 onboarding 等）
- 调 LLM 分类 intent
- 返回 Intent 枚举 + intent_args

设计原则：
- 不持久化 session（每次重新拼 messages）
- 分类失败时保守返回 CHAT，让管家兜底
- intent_args 由 LLM 同步输出（如 CREATE_PROJECT 的初始 idea、OPEN_PROJECT 的项目名关键词）

对应 spec.md §4.2
"""
from __future__ import annotations

import json
from pydantic import BaseModel, Field
from string import Template
from typing import Optional

from backend.adapters.llm_adapter import get_llm_adapter
from backend.adapters.types import ModelRole
from backend.agent.runtime.state import Intent
from backend.utils.logger import logger as logger_decorator


# ============ IntentArgs Pydantic Schema ============

class IntentArgs(BaseModel):
    """意图参数（intent-specific payload）

    不同 intent 用不同字段，其余字段留空
    """
    # CREATE_PROJECT: 用户的初始 idea（自由文本）
    initial_idea: Optional[str] = None

    # OPEN_PROJECT: 用户提到的项目名（可能模糊/部分名）
    project_name_hint: Optional[str] = None

    # LIST_PROJECTS / QUERY_PROJECTS / RECOMMEND_PROJECTS: 筛选条件
    filter_genre: Optional[str] = None
    filter_style: Optional[str] = None
    filter_status: Optional[str] = None

    # ADJUST_GLOBAL_PREFERENCE: 偏好名 + 新值
    preference_key: Optional[str] = None
    preference_value: Optional[str] = None

    # INTERVENE / ADJUST_BASE: 干预/调整的具体描述
    intervention_text: Optional[str] = None


class IntentResult(BaseModel):
    """意图识别结果"""
    intent: Intent
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    args: IntentArgs = Field(default_factory=IntentArgs)
    reasoning: str = ""  # LLM 的判断依据（用于调试）


# ============ IntentRecognizer 主类 ============

@logger_decorator
class IntentRecognizer:
    """意图识别器（管家内部组件）

    使用方式：
        recognizer = IntentRecognizer()
        result = await recognizer.classify(
            user_message="我想写个赛博朋克爱情",
            context={"has_project": False, "project_id": None},
        )
        # result.intent == Intent.CREATE_PROJECT
        # result.args.initial_idea == "赛博朋克爱情"
    """

    # ─── System Prompt ─────────────────────────────────────
    CLASSIFY_SYSTEM_PROMPT = """你是「小说管家」的意图识别模块。

【你的任务】
判断用户消息的意图，输出 JSON：
{
  "intent": "intent 名（必须小写，如 list_projects / create_project / chat）",
  "confidence": 0.0~1.0,
  "args": { intent 特定的参数 },
  "reasoning": "判断依据"
}

【严格输出规则】
- intent 字段必须使用下面 Intent 列表中的小写名字（不要大写、不要加 Intent. 前缀）
- 如果输出其他名字会被识别失败、默认降为 chat

【Intent 列表】

**项目级 intent（需有 project 上下文）**：
- GENERATE: 生成下一章
  - args: 无
  - 例: "继续写"、"生成下一章"、"写下一章"
- INTERVENE: 剧情干预
  - args: {"intervention_text": "干预描述"}
  - 例: "把师父改成反派"、"让主角遇到一个神秘人物"
- ROLLBACK: 回档
  - args: 无
  - 例: "回到第 3 章"、"回档到上一章"
- ADJUST_BASE: 调整基座
  - args: {"intervention_text": "调整描述"}
  - 例: "改主角年龄"、"调整风格更硬核"

**用户级 intent（无需 project 上下文）**：
- LIST_PROJECTS: 列出项目
  - args: 无
  - 例: "我有哪些小说"、"看看我的项目"
- QUERY_PROJECTS: 按条件筛选项目
  - args: {"filter_genre": "题材", "filter_style": "风格", "filter_status": "状态"}
  - 例: "古风的有什么"、"完结的项目"
- RECOMMEND_PROJECTS: 推荐项目
  - args: {"filter_genre": "...", "filter_style": "..."}
  - 例: "推荐几部爽文"、"推荐个治愈的"
- CREATE_PROJECT: 创建项目（启动 Onboarding）
  - args: {"initial_idea": "用户的初始想法"}
  - 例: "我想写个赛博朋克爱情故事"、"新开一个项目"
- OPEN_PROJECT: 进入项目
  - args: {"project_name_hint": "用户提到的项目名（模糊也行）"}
  - 例: "打开《赛博黑客》"、"去赛博那个"、"我想看看黑客那个"
- ADJUST_GLOBAL_PREFERENCE: 调整全局偏好
  - args: {"preference_key": "偏好名", "preference_value": "新值"}
  - 支持的偏好: default_exploration_level（值: conservative/standard/wild）
  - 例: "以后默认探索度用 standard"、"默认都用标准"
- CHAT: 闲聊/问答/不确定
  - args: 无
  - 例: "AI 创作有什么技巧"、"你好"、"随便聊聊"

【上下文】
${context_block}

【注意】
1. 意图分类要保守，不确定时选 CHAT
2. 用户消息带问号但确实是请求的（如"有哪些古风的？"）按意图判断，不是 CHAT
3. args 字段必须按上面的 schema 输出，其他字段不写
4. confidence < 0.6 时也选 CHAT，让管家兜底追问

【用户消息】
${user_message}

只输出 JSON，不要其他内容。
"""

    async def classify(
        self,
        user_message: str,
        has_project: bool = False,
        project_id: Optional[str] = None,
        in_onboarding: bool = False,
    ) -> IntentResult:
        """意图识别主入口

        Args:
            user_message: 用户消息文本
            has_project: 当前是否在某个项目内（阅读页 = True，首页 = False）
            project_id: 当前项目 ID（如果有）
            in_onboarding: 是否在 onboarding 流程中（Step 3/4 多轮对话）

        Returns:
            IntentResult（含 intent + args + confidence）
        """
        self.log.info(
            "IntentRecognizer.classify START: has_project=%s, project_id=%s, "
            "in_onboarding=%s, msg_len=%d",
            has_project, project_id, in_onboarding, len(user_message or ""),
        )

        # 拼上下文
        context_parts = []
        if in_onboarding:
            context_parts.append("- 状态：在 onboarding 流程中（用户回复管家追问）")
        elif has_project:
            context_parts.append(f"- 状态：在项目内（project_id={project_id}）")
        else:
            context_parts.append("- 状态：在管家大厅（首页，无项目上下文）")

        # 列出当前上下文可用的 intent（提示 LLM 缩小范围）
        if in_onboarding:
            context_parts.append("- 当前可用的 intent: ONBOARDING_CONTINUE, CHAT")
        elif has_project:
            context_parts.append("- 当前可用的 intent: GENERATE, INTERVENE, ROLLBACK, ADJUST_BASE, CHAT")
        else:
            context_parts.append("- 当前可用的 intent: LIST_PROJECTS, QUERY_PROJECTS, RECOMMEND_PROJECTS, CREATE_PROJECT, OPEN_PROJECT, ADJUST_GLOBAL_PREFERENCE, CHAT")

        context_block = "\n".join(context_parts)

        # 用 Template（不处理 { }，避免 prompt 里的 JSON 示例被误处理）
        sys_prompt = Template(self.CLASSIFY_SYSTEM_PROMPT).safe_substitute(
            context_block=context_block,
            user_message=user_message,
        )

        try:
            adapter = get_llm_adapter()
            self.log.debug(
                "IntentRecognizer.classify LLM CALL: context=%s",
                context_parts[1] if len(context_parts) > 1 else context_parts[0],
            )
            response = await adapter.complete_with_messages(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=sys_prompt,
                max_tokens=500,
                temperature=0.1,  # 低温度让分类更稳定
                role=ModelRole.TEXT,
            )

            # 解析 LLM 输出
            raw = response.content.strip()
            self.log.debug(
                "IntentRecognizer.classify LLM RESPONSE: raw_len=%d, preview=%s",
                len(raw), raw[:100].replace("\n", " "),
            )

            # 处理可能的 markdown 包裹
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            parsed = json.loads(raw)

            # 转 Intent 枚举（容错大小写 + 带前缀）
            intent_str = parsed.get("intent", "chat").lower().strip()
            # 去掉可能的 "Intent.CHAT" / "intent: chat" 等修饰
            if "." in intent_str:
                intent_str = intent_str.split(".")[-1]
            try:
                intent = Intent(intent_str)
            except ValueError:
                self.log.warning(
                    "IntentRecognizer.classify: 未知 intent '%s', 兜底为 CHAT",
                    parsed.get("intent"),
                )
                intent = Intent.CHAT

            args_data = parsed.get("args", {}) or {}
            args = IntentArgs(**args_data)

            confidence = float(parsed.get("confidence", 0.5))
            reasoning = parsed.get("reasoning", "")

            # 🔴 LLM 有时 intent 填错，但 args 填对。用 args 反推 intent 兜底
            original_intent = intent
            if intent == Intent.CHAT:
                if args.intervention_text:
                    intent = Intent.INTERVENE
                    self.log.info(
                        "IntentRecognizer.classify: intent=CHAT 但 args 有 intervention_text → 兜底为 INTERVENE",
                    )
                elif args.preference_key:
                    intent = Intent.ADJUST_GLOBAL_PREFERENCE
                    self.log.info(
                        "IntentRecognizer.classify: intent=CHAT 但 args 有 preference_key → 兜底为 ADJUST_GLOBAL_PREFERENCE",
                    )
                elif args.project_name_hint:
                    intent = Intent.OPEN_PROJECT
                    self.log.info(
                        "IntentRecognizer.classify: intent=CHAT 但 args 有 project_name_hint → 兜底为 OPEN_PROJECT",
                    )
                elif args.filter_genre or args.filter_style or args.filter_status:
                    intent = Intent.QUERY_PROJECTS
                    self.log.info(
                        "IntentRecognizer.classify: intent=CHAT 但 args 有 filter_* → 兜底为 QUERY_PROJECTS",
                    )
                elif args.initial_idea:
                    intent = Intent.CREATE_PROJECT
                    self.log.info(
                        "IntentRecognizer.classify: intent=CHAT 但 args 有 initial_idea → 兜底为 CREATE_PROJECT",
                    )

            # 保守兜底：confidence < 0.6 → CHAT（但上面 args 反推后不兜底）
            if confidence < 0.6 and intent == Intent.CHAT:
                # confidence 低且 args 无任何线索 → 保持 CHAT
                pass

            self.log.info(
                "IntentRecognizer.classify DONE: intent=%s, confidence=%.2f, "
                "args_keys=%s, reasoning=%s",
                intent.value, confidence,
                [k for k, v in args.model_dump().items() if v is not None],
                reasoning[:80] if reasoning else "",
            )

            return IntentResult(
                intent=intent,
                confidence=confidence,
                args=args,
                reasoning=reasoning,
            )

        except Exception as e:
            self.log.error(
                "IntentRecognizer.classify FAILED: error=%s, 兜底为 CHAT", e,
                exc_info=True,
            )
            return IntentResult(
                intent=Intent.CHAT,
                confidence=0.0,
                args=IntentArgs(),
                reasoning=f"LLM 调用失败: {e}",
            )


# ============ 工厂方法 ============

_recognizer_instance: Optional[IntentRecognizer] = None


def get_intent_recognizer() -> IntentRecognizer:
    """获取单例 IntentRecognizer"""
    global _recognizer_instance
    if _recognizer_instance is None:
        _recognizer_instance = IntentRecognizer()
    return _recognizer_instance