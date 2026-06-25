"""novel_steward — 小说管家（v0.6 顶层 Agent 之一）

职责（对应 spec.md §3.1）：
1. 唯一用户入口（所有 user_message 都先到管家）
2. 意图识别（IntentRecognizer.classify）
3. 路由分发（根据 intent 转发到 文笔家 / 世界树管理 / 内部处理）
4. 接管 Onboarding（5 步流程由管家自主驱动）
5. 结果聚合（组织对用户友好的回复）

关键设计：
- 不持久化 session（每次重新拼 messages）
- 不直接修改世界树基座（转发给世界树管理）
- 不直接生成章节正文（转发给文笔家）
- 管家只负责「听懂用户 → 找对人 → 回话」

对应 spec.md §3.1
"""
from __future__ import annotations

from pydantic import BaseModel
from typing import Optional

from backend.utils.logger import logger as logger_decorator


# ============ 管家响应结构 ============

class StewardResponse(BaseModel):
    """管家响应结构（标准 schema）"""
    intent: str
    confidence: float
    response: str
    structured_data: dict = {}
    downstream_called: Optional[str] = None


# ============ 管家系统提示 (v0.6.1 ReAct loop) ============

STEWARD_SYSTEM_PROMPT = """你是「小说管家」NovelSteward，霁月系统唯一对外接口。

【身份】
所有用户消息都由你接——首页聊天、项目内聊天、创建项目、修改偏好、闲聊问答都是你。
你不在调用其他 Agent；你使用【可用工具】自主决定行动。

【路由职责】
你的任务不是 "猜意图调下游 Agent"，而是 **使用工具自主推演**：
- 查项目数据：调 load_project / search_memory
- 创建项目：调 onboarding_start，启动 5 步引导，逐步调用 onboarding_propose_step + onboarding_user_confirm
- 生成第 1 章：在 Onboarding 5 步走完后调 onboarding_generate_chapter
- 调整项目内基座：调 edit_artifact（会走一致性检查）
- 调整全局偏好：调 adjust_global_preference（写入 user_preferences）
- 生成封面/插图：调 generate_image

【重要：不要越权】
- 你不直接修改世界树 7 件以外的表（会让一致性检查错乱）
- 你不调可能影响其他 Agent 决策的 internal_* 工具
- 如果用户问的能力你没有工具，说出来「这个需要创建项目后才能操作」

【Onboarding 5 步 (你自己推)】
当用户表达「想写」「创建项目」「我有设定」这类意图时：
1. 调 onboarding_start(project_name, idea) — 内部创建项目骨架，返回 project_id
2. 调 onboarding_propose_step(project_id, step=1) — LLM 从用户 idea 抽题材/风格/基调
3. 调 onboarding_propose_step(project_id, step=2) — LLM 选 palette
4. 调 onboarding_propose_step(project_id, step=3) — LLM 提议故事核心；调完后告诉用户预期：「这一步会定主角是谁、要面对什么冲突」，调 onboarding_user_confirm(user_response) 记录用户反馈
5. 调 onboarding_propose_step(project_id, step=4) — LLM 提议大纲；同样调 onboarding_user_confirm
6. 调 onboarding_generate_chapter(project_id) — 生成第 1 章

【闲聊】
如果用户只是闲聊、问创作技巧、问系统能力等：
- 直接用语言回答，不要乱调工具
- 不知道就说不知道
- 提示用户可以做什么（创建项目、调整偏好等）

【记忆上下文】
你会看到历史对话（7 轮基底 + 本轮 15 轮叠加）：
- 识别用户是否在继续上一个话题
- 如果是，参考历史补充上下文
- 如果不是，按新话题处理

【输出风格】
- 简洁、有温度
- 不要重复「我是什么 AI」这类 metadata
- 调完工具后最终回一句话告诉用户结果
"""


# ============ NovelSteward 主类 ============

@logger_decorator
class NovelSteward:
    """小说管家（v0.6 顶层 Agent）

    使用方式：
        steward = NovelSteward()
        result = await steward.receive(
            user_message="我想写个赛博朋克爱情",
            project_id=None,  # 首页无 projectId
            user_id="wuyu49",
        )
        # result = {
        #   "intent": "create_project",
        #   "response": "听起来很棒！能详细说说...",
        #   "structured_data": {},
        #   "downstream_called": None,
        # }
    """

    def __init__(
        self,
        executor=None,
    ):
        # v0.6.1: 管家是单一 ReAct agent, 只依赖 executor
        from backend.agent.runtime.executor import get_agent_executor
        self.executor = executor or get_agent_executor()

    # ─── 入口方法 ──────────────────────────────────

    async def receive(
        self,
        user_message: str,
        project_id: Optional[str] = None,
        user_id: str = "default",
        in_onboarding: bool = False,
        conversation_id: Optional[str] = None,
    ) -> dict:
        """管家接收用户消息的主入口 (v0.6.1 ReAct loop)

        v0.6.1 重写: 走 executor.execute() ReAct loop, 不再调 intent_recognizer 预分类
        - 单一身份: 所有用户消息 (首页 chat / 项目内 chat / 闲聊 / 创建项目) 都进 ReAct
        - 管家在 loop 里自主调 LLM + tools 决定行动
        - tools 包含 5 个原 AGENT_TOOLS + 3 个 onboarding 推进工具

        Args:
            user_message: 用户消息文本
            project_id: 项目 ID (None = 管家大厅模式, 闲聊/创建项目)
            user_id: 用户 ID
            in_onboarding: 是否在 onboarding 流程中 (v0.6.1 保留参数, 但走 ReAct 后语义弱化)
            conversation_id: 对话 ID (历史 messages 落库时用, 当前未读取)

        Returns:
            {
                "intent": "chat",  # 永远是 chat, 因为管家不分模式
                "confidence": 1.0,
                "response": str,  # 管家给用户的最终回复
                "structured_data": dict,  # 工具调用结果 (项目列表/生成章节详情等)
                "downstream_called": str | None,  # 调过哪些 tool
                "tool_calls_history": list,  # 详细 tool_calls 记录
            }
        """
        self.log.info(
            "NovelSteward.receive START: user_id=%s, project_id=%s, "
            "in_onboarding=%s, msg_len=%d, conv_id=%s",
            user_id, project_id, in_onboarding,
            len(user_message or ""), conversation_id,
        )

        # 1. 拿 history (7+15 滑动窗口)
        from backend.agent.context._helpers import load_chat_history
        try:
            history = await load_chat_history(
                user_id=user_id,
                base_rounds=7,
                session_rounds=15,
            )
        except Exception as e:
            self.log.warning("load_chat_history 失败, 用空 history: %s", e, exc_info=True)
            history = []

        # 2. 调 executor.execute() 走 ReAct loop
        from backend.agent.runtime.executor import AgentConfig
        cfg = AgentConfig(
            agent_name="novel_steward",
            system_prompt=STEWARD_SYSTEM_PROMPT,
        )
        executor_output = await self.executor.execute(
            agent=cfg,
            user_message=user_message,
            project_id=project_id,
            max_iterations=10,  # 管家调用工具多 (Onboarding 5 步), 给足轮次
            context={"conversation_id": conversation_id} if conversation_id else None,
        )

        self.log.info(
            "NovelSteward.receive DONE: iterations=%d, tool_calls=%d, "
            "response_len=%d, user_id=%s",
            executor_output.iterations, len(executor_output.tool_calls_history),
            len(executor_output.final_response or ""), user_id,
        )

        # 3. 包装返回 (前端 ws_manager 期望的 schema)
        return {
            "intent": "chat",
            "confidence": 1.0,
            "response": executor_output.final_response or "(无响应)",
            "structured_data": {},
            "downstream_called": None,  # v0.6.1: 实际调过的 tool 见 tool_calls_history
            "tool_calls_history": executor_output.tool_calls_history,
            "iterations": executor_output.iterations,
            "duration_ms": executor_output.duration_ms,
            "error": executor_output.error,
        }


# ============ 工厂方法 ============

_steward_instance: Optional[NovelSteward] = None


def get_novel_steward() -> NovelSteward:
    """获取单例 NovelSteward"""
    global _steward_instance
    if _steward_instance is None:
        _steward_instance = NovelSteward()
    return _steward_instance
