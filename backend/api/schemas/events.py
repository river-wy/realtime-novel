"""WS 事件 Pydantic Schema（从 ws_manager.py 拆出）

所有 WebSocket 推送事件的结构定义，与业务逻辑解耦。
"""
from __future__ import annotations

from pydantic import BaseModel
from typing import Optional


# ============ 通用聊天事件 ============

class AgentThinkingEvent(BaseModel):
    type: str = "agent_thinking"
    content: str


class ToolCallingEvent(BaseModel):
    type: str = "tool_calling"
    tool: str
    args: dict


class ToolResultEvent(BaseModel):
    type: str = "tool_result"
    tool: str
    result: dict


class AgentMessageEvent(BaseModel):
    type: str = "agent_message"
    content: str


class ErrorEvent(BaseModel):
    type: str = "error"
    code: str
    message: str


class InterruptedEvent(BaseModel):
    type: str = "interrupted"
    message: str


class ConfirmRequiredEvent(BaseModel):
    type: str = "confirm_required"
    action: str
    details: dict


# ============ Onboarding 事件 ============

class OnboardingProposalEvent(BaseModel):
    """Agent 提议 Step 3/4 4 字段"""
    type: str = "onboarding_proposal"
    step: int  # 3 or 4
    fields: dict  # 4 字段 dict


class OnboardingConfirmedEvent(BaseModel):
    """用户确认后, Agent 写 7 件完成"""
    type: str = "onboarding_confirmed"
    step: int  # 3 or 4
    fields: dict
    artifacts_written: list  # 写入了哪些基座表 (e.g. ['main_plot', 'seed_table'])


class OnboardingStepDoneEvent(BaseModel):
    """Step 3/4 完成, 跳下一步"""
    type: str = "onboarding_step_done"
    step: int  # 3 or 4
    next_step: Optional[int]  # 4 or 5 or None

