"""realtime_novel v0.4 持久化层 Pydantic Schema

对应 spec.md §4.1 新增 5 张表 + chapter_status + projects_deleted
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ============ Enums ============

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChapterState(str, Enum):
    IDLE = "idle"
    GENERATING = "generating"
    DONE = "done"
    FAILED = "failed"


# ============ Tables ============

class Conversation(BaseModel):
    id: str
    project_id: Optional[str] = None
    user_id: str
    created_at: datetime
    last_active_at: datetime


class Message(BaseModel):
    id: str
    conversation_id: str
    role: MessageRole
    content: Optional[str] = None
    tool_calls: Optional[dict[str, Any]] = None
    tool_results: Optional[dict[str, Any]] = None
    thinking: Optional[dict[str, Any]] = None
    created_at: datetime


class ToolCallLog(BaseModel):
    id: str
    message_id: Optional[str] = None
    tool_name: str
    args: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
    duration_ms: int
    created_at: datetime


class AgentState(BaseModel):
    thread_id: str
    checkpoint_data: dict[str, Any]
    updated_at: datetime


class UserPreference(BaseModel):
    user_id: str
    key: str
    value: Optional[str] = None
    updated_at: datetime


class ChapterStatus(BaseModel):
    project_id: str
    chapter_num: int
    status: ChapterState
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class ProjectDeleted(BaseModel):
    project_id: str
    original_name: str
    palette: str
    deleted_at: datetime
    trash_path: Optional[str] = None
    seven_artifacts_yaml: Optional[str] = None
    world_tree_json: Optional[str] = None
