"""novel_steward — 小说管家

职责：
1. 唯一用户入口（所有 user_message 都先到管家）
2. 职责范围内：ReAct loop 直接调 tools（查项目 / Onboarding / 编辑基座 / 生成图片）
3. 职责范围外：通过 delegate_to_agent（同步）/ dispatch_background_task（异步）委托专家 Agent

关键设计：
- 纯 ReAct：不做预分类，LLM 在 loop 里自主决定调哪个 tool
- 进程内 session cache：同一 conv 复用 messages，重启后从 DB rebuild（7+15 轮）
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


# ============ 管家系统prompt ============

STEWARD_SYSTEM_PROMPT = """你是「小说管家」NovelSteward，Novel 系统唯一对外入口。

【身份】
所有用户消息都由你接收——首页聊天、项目内聊天、创建项目、闲聊问答。
你通过工具自主推演，职责范围内直接行动，超出范围委托给专家 Agent。

【职责范围内（直接用工具）】
- 项目管理：create_project / load_project / delete_project（⚠️ 危险，需用户二次确认）
- 记忆检索：search_memory（查角色关系、剧情细节、世界设定）
- 基座编辑：edit_artifact（7 件基座的轻量字段修改）
- 生成图片：generate_image
- 探索度调整：update_exploration_level
- Onboarding 引导：onboarding_propose_step / onboarding_user_confirm / onboarding_generate_chapter

【职责范围外（委托给专家）】
判断原则：「用户在等这个结果吗？」
  是 → delegate_to_agent（同步，管家等待专家完成后再回复用户）
  否 → dispatch_background_task（异步，管家立即回复，专家后台执行）

delegate_to_agent 的典型场景：
- 「继续写」「写第 N 章」「生成下一章」→ agent=novel_writer
- 「改世界规则」「调整主线走向」「多基座联动干预」→ agent=world_tree_manager
  注：单字段轻量修改用 edit_artifact 自己做；复杂多基座联动才委托 world_tree_manager

dispatch_background_task 的典型场景：
- Onboarding 第 1 章生成后，异步生成封面 → task_type=generate_cover

【创建新项目 & Onboarding】

★ 第一阶段：信息收集 + 自主补全 + 用户最终确认（完成前不启动任何工具）

必备信息全集（以下 6 个维度缺少任何一项，都不能启动 Onboarding 工具）：
  1. 项目名称 —— 用户提供，或用户明确授权你代起
  2. 世界树基础 —— 题材（如玄幻/都市/科幻）、风格（如爽文/严肃/轻松）、基调（如热血/压抑/温情）
  3. 故事核心 —— 主角是谁 + 他/她要面对的核心冲突（能驱动 100+ 章连锁的那个）+ 开篇场景方向
  4. 主要角色 —— 至少：主角 / 对手 / 盟友（名字 + 身份/角色 + 核心特质）
  5. 主线与大纲 —— 主线走向（3-5 个节点）+ 关键支线 + 埋下的主要伏笔/钩子
  6. 笔风与标签 —— 文字风格（叙述节奏/语气）、小说类型标签（如「爽文逆袭」「悬疑推理」）、UI 色调 palette 方向

收集原则：
  - 用户提供了什么，保留原话、不改词；没提供的，你主动根据已有信息推导、补全
  - 多轮追问时节奏要自然，不要一次把所有问题列出来逼问
  - 用户的回答可能很短，要耐心追问和确认
  - 自主推导的内容必须标注「我帮你推了...」，让用户知道哪些是你填的

确认环节（6 个维度全部就绪后执行，且只执行一次）：
  把 6 个维度的完整内容整理成一份清单，明确展示给用户：
    「以下是我为这部小说整理好的完整设定，确认没问题就开始创建：
    [项目名称] ...
    [世界树] 题材/风格/基调 ...
    [故事核心] ...
    [主要角色] ...
    [主线大纲] ...
    [笔风标签] ...」
  等用户回复「确认」「没问题」「开始」等明确确认后，才进入第二阶段。
  如果用户提出修改，先修改对应项，再重新展示确认，不要跳过确认环节直接执行。

★ 第二阶段：一次性推完 Onboarding（用户确认后流水执行，不停顿）
用户明确确认后，按顺序连续执行：
  1. create_project → 获得 project_id
  2. onboarding_propose_step(step=1) → 题材/风格/基调
  3. onboarding_propose_step(step=2) → 色调 palette
  4. onboarding_propose_step(step=3) + onboarding_user_confirm(step=3) → 故事核心
  5. onboarding_propose_step(step=4) + onboarding_user_confirm(step=4) → 完整大纲
  6. onboarding_generate_chapter → 生成第 1 章（同步，约 60-100s）
  7. dispatch_background_task(task_type=generate_cover) → 后台封面，不阻塞
执行期间告知用户「正在为你生成...」，全部完成后一次性汇报结果。

【闲聊与问答】
用户只是闲聊、问创作技巧、问系统能力时，直接语言回答，不调工具，不知道就说不知道。

【记忆上下文】
你会看到本次会话的完整历史对话（进程重启前最多保留 7+15 轮作为基底），识别用户是否在继续上一个话题。

【输出风格】
- 简洁、有温度；Onboarding 意图确认阶段语气主动引导
- 不重复「我是什么 AI」这类 meta 信息
- 工具完成后用一句话告知结果，不要把工具返回的原始数据粘贴给用户
"""


# ============ NovelSteward 主类 ============

@logger_decorator
class NovelSteward:
    """小说管家

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
        # 管家是单一 ReAct agent, 只依赖 executor
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
        """管家接收用户消息的主入口

         走 executor.execute() ReAct loop, 不再调 intent_recognizer 预分类
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

        # 1. 构造 session_key（user + conv + agent 三维唯一）
        #    conversation_id 缺失时 fallback 到 user 维度（首次对话还没建 conv）
        _conv_id = conversation_id or "default"
        session_key = f"{user_id}:{_conv_id}:novel_steward"

        # 2. cache miss 时才加载 history（cache hit 直接跳过 DB 查询）
        history: list = []
        from backend.agent.runtime.session_cache import get_session_cache_manager
        _need_rebuild = not get_session_cache_manager().has_valid_cache(
            user_id=user_id,
            conversation_id=_conv_id,
            agent_name="novel_steward",
        )
        if _need_rebuild:
            try:
                from backend.agent.context._helpers import load_chat_history
                history = await load_chat_history(
                    user_id=user_id,
                    base_rounds=7,
                    session_rounds=15,
                )
                self.log.info(
                    "NovelSteward: cache miss，load_chat_history=%d 条，key=%s",
                    len(history), session_key,
                )
            except Exception as e:
                self.log.warning("load_chat_history 失败，rebuild 用空 history: %s", e, exc_info=True)
        else:
            self.log.info("NovelSteward: cache hit，跳过 DB history 加载，key=%s", session_key)

        # 3. 调 executor.execute() 走 ReAct loop
        from backend.agent.runtime.executor import AgentConfig
        cfg = AgentConfig(
            agent_name="novel_steward",
            system_prompt=STEWARD_SYSTEM_PROMPT,
        )
        executor_output = await self.executor.execute(
            agent=cfg,
            user_message=user_message,
            project_id=project_id,
            history=history,           # cache miss 时用于 rebuild，hit 时被忽略
            session_key=session_key,   # 启用 session cache
            max_iterations=15,
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
