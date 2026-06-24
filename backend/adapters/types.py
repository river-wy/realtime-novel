"""LLM Adapter Types - Pydantic Schema

对应 infra.md §B.2.2 + novel-llm-adapter.json
v0.4.1: LLMRequest 加 messages 字段，支持多轮对话上下文
v0.6: 加 tools/tool_choice 字段（OpenAI function calling 支持）
v0.6: LLMResponse 加 tool_calls 字段
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


class ModelRole(str, Enum):
    """调用角色"""
    TEXT = "text"      # 推理/对话 → friday/deepseek-v4-pro-tencent
    IMAGE = "image"    # 图片生成 → friday/gemini-3.1-flash-image-preview


class ModelProvider(str, Enum):
    # v0.7: 加 friday/ 前缀表示「提供方」，未来会有 deepseek/xxx,minimax/xxx 原生
    DEEPSEEK = "friday/deepseek-v4-pro-tencent"
    GEMINI = "friday/gemini-3.1-flash-image-preview"


class LLMRequest(BaseModel):
    """统一的 LLM 调用请求

    v0.4.1 扩展：加 messages 字段（标准 OpenAI 格式）
    v0.6 扩展：加 tools / tool_choice 字段（OpenAI function calling）
    """
    prompt: str = Field(default="", min_length=0)
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    role: ModelRole = ModelRole.TEXT
    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: int = Field(8192, ge=1, le=16384)
    system_prompt: Optional[str] = None
    stream: bool = False
    response_format: Optional[Dict[str, Any]] = None
    frequency_penalty: float = Field(default=0.0, ge=-2, le=2)
    presence_penalty: float = Field(default=0.0, ge=-2, le=2)
    enable_thinking: bool = True

    # ─── v0.6 OpenAI Function Calling ──────────────────
    tools: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="OpenAI tools 格式列表，每个元素是 {type: 'function', function: {name, description, parameters}}",
    )
    tool_choice: Optional[Any] = Field(
        default=None,
        description="'auto' | 'none' | 'required' | {type: 'function', function: {name: ...}}",
    )


class ToolCallFunction(BaseModel):
    """LLM 调用的 function 详情（OpenAI 格式）"""
    name: str
    arguments: str  # JSON 字符串，调用方需手动 json.loads


class ToolCall(BaseModel):
    """LLM 输出的一次 tool 调用（OpenAI 格式）"""
    id: str
    type: str = "function"
    function: ToolCallFunction


class LLMResponse(BaseModel):
    """同步调用响应

    v0.6 扩展：加 tool_calls 字段，LLM 决定调工具时填这个
    - 有 tool_calls 时 content 通常为空（LLM 只输出 tool_call）
    - 无 tool_calls 时 content 是 LLM 文本回复
    """
    content: str = ""
    tool_calls: Optional[List[ToolCall]] = None
    provider: ModelProvider
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    cached: bool = False


class LLMStreamChunk(BaseModel):
    """流式输出 chunk（含 thinking reasoning_content）

    v0.6 扩展：加 tool_calls_delta 字段，流式累积 tool_calls
    """
    delta: str = ""
    reasoning: str = ""
    provider: ModelProvider
    is_final: bool = False
    finish_reason: Optional[str] = None
    # v0.6 新增：流式 tool_calls 增量（OpenAI 协议按 fragment 返回）
    tool_calls_delta: Optional[List[Dict[str, Any]]] = None
