"""api.schemas 包：WS 事件 Pydantic Schema

v0.6.2 简化:
- 删 Onboarding 相关 schema (HTTP /onboarding 路由 + WS onboarding_request_proposal/confirm handler 都已删除)
- OnboardingProposalEvent / OnboardingConfirmedEvent / OnboardingStepDoneEvent 保留定义（兼容历史消息）, 不再主动发送
"""
from backend.api.schemas.events import (
    AgentThinkingEvent,
    ToolCallingEvent,
    ToolResultEvent,
    AgentMessageEvent,
    ErrorEvent,
    InterruptedEvent,
    ConfirmRequiredEvent,
    # Onboarding 事件保留定义（兼容历史消息）, 不再主动发送
    OnboardingProposalEvent,
    OnboardingConfirmedEvent,
    OnboardingStepDoneEvent,
)

__all__ = [
    # WS 通用事件
    "AgentThinkingEvent",
    "ToolCallingEvent",
    "ToolResultEvent",
    "AgentMessageEvent",
    "ErrorEvent",
    "InterruptedEvent",
    "ConfirmRequiredEvent",
    # Onboarding 事件保留定义（兼容历史消息）, 不再主动发送
    "OnboardingProposalEvent",
    "OnboardingConfirmedEvent",
    "OnboardingStepDoneEvent",
]