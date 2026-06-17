"""LLM Adapter Types - Pydantic Schema

对应 infra.md §B.2.2 + novel-llm-adapter.json
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ModelRole(str, Enum):
    """调用角色"""
    TEXT = "text"      # 推理/对话 → deepseek-v4-pro-tencent
    IMAGE = "image"    # 图片生成 → gemini-3.1-flash-image-preview


class ModelProvider(str, Enum):
    DEEPSEEK = "deepseek-v4-pro-tencent"  # 带 -tencent 后缀
    GEMINI = "gemini-3.1-flash-image-preview"


class LLMRequest(BaseModel):
    """统一的 LLM 调用请求"""
    prompt: str = Field(..., min_length=1)
    role: ModelRole = ModelRole.TEXT
    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: int = Field(2048, ge=1, le=8192)
    system_prompt: Optional[str] = None
    stream: bool = False


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
