"""AgentState + Intent + ToolCall Pydantic Schemas

对应 core.md §B.2.1 + v0.6 spec.md §4.2

v0.6 扩展：
- Intent 枚举新增 6 类：ONBOARDING_CONTINUE, LIST_PROJECTS, QUERY_PROJECTS,
  RECOMMEND_PROJECTS, OPEN_PROJECT, ADJUST_GLOBAL_PREFERENCE
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class Intent(str, Enum):
    """管家决策的 intent（v0.6 完整版）

    分为两组：
    - 项目级（需 project_id 上下文）：GENERATE, INTERVENE, ROLLBACK, ADJUST_BASE, ONBOARDING_CONTINUE
    - 用户级（无需 project_id）：LIST_PROJECTS, QUERY_PROJECTS, RECOMMEND_PROJECTS,
                                 CREATE_PROJECT, OPEN_PROJECT, ADJUST_GLOBAL_PREFERENCE, CHAT
    """
    # ─── 项目级（v0.4 已有） ─────────────────────
    GENERATE = "generate"               # 生成下一章 → 小说文笔家
    INTERVENE = "intervene"             # 剧情干预 → 世界树管理
    ROLLBACK = "rollback"               # 回档（危险）→ 管家直处理
    ADJUST_BASE = "adjust_base"         # 调整基座 → 世界树管理
    CHAT = "chat"                       # 闲聊（项目级/用户级共用）

    # ─── 项目级（v0.6 新增） ─────────────────────
    ONBOARDING_CONTINUE = "onboarding_continue"  # Onboarding 多轮对话 → 管家内部

    # ─── 用户级（v0.6 新增，管家大厅） ─────────
    LIST_PROJECTS = "list_projects"                   # "我有哪些小说"
    QUERY_PROJECTS = "query_projects"                 # "古风的有什么"
    RECOMMEND_PROJECTS = "recommend_projects"         # "推荐几部爽文"
    CREATE_PROJECT = "create_project"                 # "我想写个..." → Onboarding
    OPEN_PROJECT = "open_project"                     # "打开《赛博》"
    ADJUST_GLOBAL_PREFERENCE = "adjust_global_pref"   # "以后默认 standard"


class ToolCall(BaseModel):
    """工具调用记录"""
    tool_name: str
    args: dict
    result: Optional[dict] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class ExpertOpinion(BaseModel):
    """专家 Agent 咨询结果（v0.4 stub → v0.6 已废除，仅保留 schema）"""
    expert_name: str
    opinion: str
    confidence: float = Field(..., ge=0, le=1)
    suggested_actions: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    """管家处理的统一状态（v0.6）

    替代 v0.4 的 LangGraph StateGraph 状态，作为管家 receive() 方法的入参/出参
    """
    # ─── 输入 ──────────────────────────────
    user_message: str = ""
    project_id: Optional[str] = None
    conversation_id: str = ""
    message_id: str = ""

    # ─── 中间态（intent 识别后填充）─────
    intent: Optional[Intent] = None
    intent_args: dict = Field(default_factory=dict)
    plan: Optional[str] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)

    # ─── 上下文 ──────────────────────────
    messages: list[dict[str, Any]] = Field(default_factory=list)  # 历史 messages 表
    project_context: dict = Field(default_factory=dict)            # 当前项目快照（项目级 intent 用）

    # ─── 输出 ──────────────────────────────
    final_response: Optional[str] = None
    structured_data: dict = Field(default_factory=dict)  # 结构化数据（如项目列表、跳转 URL）
    error: Optional[str] = None

    # ─── 流程控制 ────────────────────────
    interrupt_requested: bool = False
    retry_count: int = 0