"""api.schemas 包：WS 事件 + Onboarding Pydantic Schema"""
from backend.api.schemas.events import (
    AgentThinkingEvent,
    ToolCallingEvent,
    ToolResultEvent,
    AgentMessageEvent,
    ErrorEvent,
    InterruptedEvent,
    ConfirmRequiredEvent,
    OnboardingProposalEvent,
    OnboardingConfirmedEvent,
    OnboardingStepDoneEvent,
)
from backend.api.schemas.onboarding import (
    OnboardingPayloadStep1,
    OnboardingPayloadStep2,
    OnboardingPayloadStep3,
    OnboardingPayloadStep4,
    OnboardingPayloadStep5,
    OnboardingPayload,
    OnboardingRequest,
    OnboardingResponse,
    validate_onboarding_payload,
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
    # WS Onboarding 事件
    "OnboardingProposalEvent",
    "OnboardingConfirmedEvent",
    "OnboardingStepDoneEvent",
    # HTTP Onboarding Schema
    "OnboardingPayloadStep1",
    "OnboardingPayloadStep2",
    "OnboardingPayloadStep3",
    "OnboardingPayloadStep4",
    "OnboardingPayloadStep5",
    "OnboardingPayload",
    "OnboardingRequest",
    "OnboardingResponse",
    "validate_onboarding_payload",
]

