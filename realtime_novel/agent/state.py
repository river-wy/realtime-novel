"""AgentState + Intent + ToolCall Pydantic Schemas

对应 core.md §B.2.1
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class Intent(str, Enum):
    """主 Agent 决策的 6 类意图（spec §6.2）"""
    GENERATE = "generate"
    INTERVENE = "intervene"
    ROLLBACK = "rollback"
    ADJUST_BASE = "adjust_base"
    CREATE_PROJECT = "create_project"
    CHAT = "chat"


class ToolCall(BaseModel):
    """工具调用记录"""
    tool_name: str
    args: dict
    result: Optional[dict] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class ExpertOpinion(BaseModel):
    """专家 Agent 咨询结果（v0.4 stub）"""
    expert_name: str
    opinion: str
    confidence: float = Field(..., ge=0, le=1)
    suggested_actions: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    """LangGraph StateGraph 的状态"""
    # 输入
    user_message: str = ""
    project_id: Optional[str] = None
    conversation_id: str = ""
    message_id: str = ""

    # 中间态
    intent: Optional[Intent] = None
    expert_opinions: list[ExpertOpinion] = Field(default_factory=list)
    plan: Optional[str] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    retry_count: int = 0

    # 输出
    final_response: Optional[str] = None
    error: Optional[str] = None

    # LangGraph 内部
    messages: list[dict[str, Any]] = Field(default_factory=list)
    interrupt_requested: bool = False

    # v0.4.1: LLM 调用的多轮上下文（从 messages 表拿，节点调 LLM 时传）
    history_messages: list[dict[str, Any]] = Field(default_factory=list)
    system_prompt: Optional[str] = None  # v0.4.1: 节点调 LLM 用的 system prompt
