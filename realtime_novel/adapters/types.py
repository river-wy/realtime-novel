"""LLM Adapter Types - Pydantic Schema

对应 infra.md §B.2.2 + novel-llm-adapter.json
v0.4.1: LLMRequest 加 messages 字段，支持多轮对话上下文
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ModelRole(str, Enum):
    """调用角色"""
    TEXT = "text"      # 推理/对话 → deepseek-v4-pro-tencent
    IMAGE = "image"    # 图片生成 → gemini-3.1-flash-image-preview


class ModelProvider(str, Enum):
    DEEPSEEK = "deepseek-v4-pro-tencent"  # 带 -tencent 后缀
    GEMINI = "gemini-3.1-flash-image-preview"


class LLMRequest(BaseModel):
    """统一的 LLM 调用请求

    v0.4.1 扩展：加 messages 字段（标准 OpenAI 格式）
    - 如果传了 messages：直接用（可包含 system / user / assistant / tool 消息）
    - 如果没传 messages：兼容旧代码，system_prompt + prompt 拼成单条 user

    v0.6 新增：response_format 强制 JSON 输出（v0.3 路径清理用）
    """
    prompt: str = Field(default="", min_length=0)  # v0.4.1 改成可空（messages 模式不需要）
    messages: List[Dict[str, Any]] = Field(default_factory=list)  # v0.4.1 新增
    role: ModelRole = ModelRole.TEXT
    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: int = Field(2048, ge=1, le=8192)
    system_prompt: Optional[str] = None
    stream: bool = False
    response_format: Optional[Dict[str, Any]] = None  # v0.6 新增：{type: "json_object"}


class LLMResponse(BaseModel):
    """同步调用响应"""
    content: str
    provider: ModelProvider
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    cached: bool = False


class LLMStreamChunk(BaseModel):
    """流式输出 chunk（含 thinking reasoning_content）"""
    delta: str = ""
    reasoning: str = ""  # 思考内容（DeepSeek Thinking 模式）
    provider: ModelProvider
    is_final: bool = False
    finish_reason: Optional[str] = None  # "stop" | "length" | "error"
