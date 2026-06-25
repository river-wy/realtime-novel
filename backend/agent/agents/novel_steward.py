"""novel_steward — 小说管家（v0.6.2 纯 ReAct 版）

职责：
1. 唯一用户入口（所有 user_message 都先到管家）
2. 职责范围内：ReAct loop 直接调 tools（查项目 / Onboarding / 编辑基座 / 生成图片）
3. 职责范围外：通过 delegate_to_agent（同步）/ dispatch_background_task（异步）委托专家 Agent

关键设计：
- 纯 ReAct：不做预分类，LLM 在 loop 里自主决定调哪个 tool
- 不持久化 session（每次重新拼 messages）
- 不直接生成章节正文（delegate_to_agent → novel_writer）
- 不直接修改世界树基座（delegate_to_agent → world_tree_manager）
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
你使用【可用工具】自主推演，职责范围内直接行动，职责范围外委托给专家 Agent。

【职责范围内（你直接用工具）】
- 查项目数据：load_project / search_memory
- 创建项目 + Onboarding 5 步引导（见下）
- 调整项目内基座：edit_artifact（含一致性检查）
- 生成封面/插图：generate_image

【职责范围外（委托给专家 Agent）】

判断原则：「用户在等这个结果吗？」
  是 → 同步委托 delegate_to_agent（管家等待专家完成后再回复用户）
  否 → 异步派发 dispatch_background_task（管家立即回复，专家后台执行）

delegate_to_agent 的场景（用户明确等待）：
- 「继续写」「生成下一章」「写第 N 章」→ agent=novel_writer
- 「把师父改成反派」「调整主线弧线」「干预剧情」→ agent=world_tree_manager
- 「修改主角年龄」「更新世界规则」等基座调整 → agent=world_tree_manager

dispatch_background_task 的场景（管家自主识别，用户不需要等）：
- 章节生成完毕后自动更新 chapter_summary → task_type=update_chapter_summary
- Onboarding 第 1 章生成后异步生成封面 → task_type=generate_cover
- 干预完成后后台重建记忆索引 → task_type=rebuild_memory_index

【Onboarding 5 步（你自己推，属于职责范围内）】
当用户表达「想写」「创建项目」「我有设定」这类意图时：
1. 调 create_project(project_name, idea) — 创建项目骨架，返回 project_id
2. 调 onboarding_propose_step(project_id, step=1) — 抽题材/风格/基调
3. 调 onboarding_propose_step(project_id, step=2) — 选 palette
4. 调 onboarding_propose_step(project_id, step=3) — 提议故事核心；告知用户期望输入；调 onboarding_user_confirm 记录反馈
5. 调 onboarding_propose_step(project_id, step=4) — 提议大纲；同样调 onboarding_user_confirm
6. 调 onboarding_generate_chapter(project_id) — 生成第 1 章（同步等待）
7. 调 dispatch_background_task(agent=image_generator, task_type=generate_cover) — 后台生成封面（不阻塞用户）

【重要：不要越权】
- 不直接修改世界树 7 件基座以外的表（会让一致性检查错乱）
- 不调 internal_* 工具（可能影响其他 Agent 决策）
- 没有对应工具时，如实告诉用户「这个能力需要在项目内操作」

【闲聊】
用户只是闲聊、问创作技巧、问系统能力时：
- 直接用语言回答，不要乱调工具
- 不知道就说不知道

【记忆上下文】
你会看到历史对话（7 轮基底 + 本轮 15 轮叠加）：
- 识别用户是否在继续上一个话题，若是则参考历史补充上下文

【输出风格】
- 简洁、有温度
- 不要重复「我是什么 AI」这类 metadata
- 调完工具后用一句话告诉用户结果（结构化数据由 structured_data 字段承载）
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
            "structured_data": executor_output.structured_data,  # 透传专家结构化结果
            "downstream_called": None,  # 实际调过的 tool 见 tool_calls_history
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
