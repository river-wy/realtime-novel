"""onboarding_controller — 管家子流程（s3.5）

职责（spec.md §3.1.1）：
1. CREATE_PROJECT intent 触发后由管家内部启动
2. 5 步流程：
   - Step 1-2: 按钮交互（题材/风格/基调 + palette）
   - Step 3-4: 管家跑 LLM 推演（多轮对话引导）
   - Step 5: 调 NovelWriter 生成第 1 章
3. 不算独立顶层 Agent（18:02 拍板：方案 B）

对应 spec.md §3.1.1
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

from backend.adapters.types import LLMRequest, ModelRole
from backend.agent.executor import AgentExecutor, get_agent_executor
from backend.agent.novel_writer import get_novel_writer

log = logging.getLogger(__name__)


# ============ Onboarding Step 枚举 ============

class OnboardingStep(str, Enum):
    """Onboarding 5 步"""
    STEP_1 = "step_1_world_tree"  # 题材/风格/基调（按钮）
    STEP_2 = "step_2_palette"      # palette（按钮）
    STEP_3 = "step_3_core"         # 核心设定（对话）
    STEP_4 = "step_4_outline"      # 大纲（对话）
    STEP_5 = "step_5_chapter"      # 生成第 1 章


# ============ Onboarding 状态 ============

class OnboardingState(BaseModel):
    """Onboarding 流程状态"""
    project_id: Optional[str] = None
    current_step: OnboardingStep = OnboardingStep.STEP_3
    history: List[dict] = Field(default_factory=list)
    completed: bool = False


class OnboardingResult(BaseModel):
    """Onboarding 单轮结果"""
    new_state: OnboardingState
    assistant_response: str
    should_generate_chapter: bool = False


class ChapterGenResult(BaseModel):
    """Step 5 生成结果"""
    chapter_content: str = ""
    chapter_summary: str = ""
    iterations: int = 0
    error: Optional[str] = None


# ============ 系统提示 ============

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


# ============ OnboardingController 主类 ============

class OnboardingController:
    """Onboarding 流程控制器（管家子模块，s3.5）

    使用方式：
        controller = get_onboarding_controller()
        result = await controller.run_step_3_or_4(
            user_message="主角是一个黑客",
            state=OnboardingState(project_id="proj-123", current_step=OnboardingStep.STEP_3),
        )
        # result.assistant_response = "好的，主角是黑客..."
        # result.should_generate_chapter = False
        # result.new_state.history 已更新
    """

    def __init__(self, executor: Optional[AgentExecutor] = None):
        self.executor = executor or get_agent_executor()

    async def run_step_3_or_4(
        self,
        user_message: str,
        state: OnboardingState,
        max_tokens: int = 2048,
        temperature: float = 0.8,
    ) -> OnboardingResult:
        """运行 Step 3 或 Step 4（多轮对话引导）

        注意：Step 3-4 主要是对话引导，不需要工具调用。
        这里直接调 LLM（不带 tools），让管家自主决策说什么。
        """
        # 拼 messages（system + state context + history + user）
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

        # 追加到 history
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

        # 判断是否触发 Step 5
        should_generate = self._should_trigger_chapter(user_message, assistant_response)
        if should_generate:
            new_state.current_step = OnboardingStep.STEP_5

        return OnboardingResult(
            new_state=new_state,
            assistant_response=assistant_response,
            should_generate_chapter=should_generate,
        )

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