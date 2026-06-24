"""backend v0.4.1 持久化层 Pydantic Schema

对应 spec.md §4.1 + v002_artifacts_to_db.sql
- v001: 5 张表（conversations/messages/tool_calls_log/agent_state/user_preferences/chapter_status/projects_deleted/world_entries_vec）
- v002: 13 张表（projects + 7 件基座 + chapters + onboarding_state + 2 张关联表）
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Literal
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


class ConversationStatus(str, Enum):
    """v0.5 新增：对话状态
    - active: 当前进行中
    - invalidated: 被新建对话取代（保留历史）
    - archived: 用户主动归档
    """
    ACTIVE = "active"
    INVALIDATED = "invalidated"
    ARCHIVED = "archived"


class CharacterRole(str, Enum):
    PROTAGONIST = "protagonist"
    DEUTERAGONIST = "deuteragonist"
    ANTAGONIST = "antagonist"
    SUPPORTING = "supporting"
    MINOR = "minor"


class SeedStatus(str, Enum):
    PLANTED = "planted"
    RESONATING = "resonating"
    HARVESTED = "harvested"
    ABANDONED = "abandoned"


class SubplotStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class SubplotPriority(str, Enum):
    MAIN = "main"
    SIDE = "side"
    MINOR = "minor"


# ============ v001 Tables ============

class Conversation(BaseModel):
    """v0.5 重构：project_id 移除（不绑 project），加 status/invalidated_at/reason/summary/message_count"""
    id: str
    user_id: str
    created_at: datetime
    last_active_at: datetime
    status: ConversationStatus = ConversationStatus.ACTIVE
    invalidated_at: Optional[datetime] = None
    reason: Optional[str] = None
    summary: Optional[str] = None  # v0.5 新增：对话压缩 summary
    message_count: int = 0  # v0.5 新增：消息计数（用于触发 summary 压缩）


class Message(BaseModel):
    """v0.5 重构：加 project_id 字段（每条消息绑 project）"""
    id: str
    conversation_id: str
    project_id: Optional[str] = None  # v0.5 新增
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


# ============ v002 Tables ============

class Project(BaseModel):
    """项目元数据（v0.4 走文件系统，v0.4.1 入 DB）"""
    id: str
    name: str
    palette: str = ""
    # v0.8: 探索度旋钮 (conservative/standard/wild)
    exploration_level: str = "standard"
    current_pov: Optional[str] = None
    # v0.9: 世界封面图 URL（相对路径 /static/projects/{id}/cover.png，null 表示未生成）
    cover_image_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class WorldTreeRow(BaseModel):
    """01-world-tree.yaml → world_tree 表"""
    project_id: str
    timeline_era: Optional[str] = None
    year_range_start: Optional[int] = None
    year_range_end: Optional[int] = None
    anchor_event: Optional[str] = None
    geography_primary: Optional[str] = None
    geography_secondary_json: Optional[str] = None  # list[str]
    geography_spatial_rules_json: Optional[str] = None  # list[str]
    core_rules_json: Optional[str] = None  # list[CoreRule]
    branches_json: Optional[str] = None  # list[TreeNode]
    metadata_json: Optional[str] = None
    updated_at: datetime


class StyleCharterRow(BaseModel):
    project_id: str
    prose_style_json: Optional[str] = None
    tone_json: Optional[str] = None
    density_json: Optional[str] = None
    taboos_json: Optional[str] = None
    notes_json: Optional[str] = None  # list[str] (adjust_style 追加)
    limits_json: Optional[str] = None
    metadata_json: Optional[str] = None
    updated_at: datetime


class GenreResonanceRow(BaseModel):
    project_id: str
    accept_json: Optional[str] = None
    reject_json: Optional[str] = None
    anchors_json: Optional[str] = None
    metadata_json: Optional[str] = None
    updated_at: datetime


class MainPlotRow(BaseModel):
    project_id: str
    current_beat: int = 0
    arc_phrase: Optional[str] = None
    beats_json: Optional[str] = None  # list[Beat]
    metadata_json: Optional[str] = None
    updated_at: datetime


class SubPlotRow(BaseModel):
    id: str
    project_id: str
    title: str
    description: Optional[str] = None
    parent_beat_id: Optional[str] = None
    status: SubplotStatus
    priority: SubplotPriority
    linked_seeds_json: Optional[str] = None
    linked_chars_json: Optional[str] = None
    beats_json: Optional[str] = None
    metadata_json: Optional[str] = None
    updated_at: datetime


class CharacterRow(BaseModel):
    id: str
    project_id: str
    name: str
    role: CharacterRole
    traits_json: Optional[str] = None
    speech_style: Optional[str] = None
    background: Optional[str] = None
    arc: Optional[str] = None
    internal_state: Optional[str] = None
    metadata_json: Optional[str] = None
    updated_at: datetime


class CharacterRelationshipRow(BaseModel):
    id: str
    project_id: str
    from_char_id: str
    to_char_id: str
    type: Optional[str] = None
    description: Optional[str] = None
    evolution_json: Optional[str] = None
    metadata_json: Optional[str] = None
    updated_at: datetime


class SeedRow(BaseModel):
    id: int
    project_id: str
    content: str
    importance_primary: str
    size: str
    planned_interval: Optional[int] = None
    orientation: str
    planted_at_chapter: int = 0
    planted_in_node: Optional[str] = None
    planted_context: Optional[str] = None
    last_seen_chapter: int = 0
    weight: float = 0.5
    status: SeedStatus
    linked_char_ids_json: Optional[str] = None
    linked_subplot_id: Optional[str] = None
    updated_at: datetime


class ChapterRow(BaseModel):
    """章节 metadata（正文走文件 `data/{project_id}/chapters/chapter_NNN.md`）"""
    project_id: str
    chapter_num: int
    title: Optional[str] = None
    summary: Optional[str] = None  # 1 句话
    detailed_summary: Optional[str] = None  # 100-200 字
    word_count: int = 0
    file_path: str
    intervention: Optional[str] = None
    actor_feedback: Optional[str] = None
    actor_character: Optional[str] = None
    generated_at: datetime
    updated_at: datetime


class OnboardingStateRow(BaseModel):
    project_id: str
    current_step: int = 0
    started_at: Optional[datetime] = None
    updated_at: datetime
    state_json: str
    artifacts_generated: bool = False
    chapter_1_generated: bool = False
    chapter_1_path: Optional[str] = None


class ChapterSeedChangeRow(BaseModel):
    id: int
    project_id: str
    chapter_num: int
    seed_id: int
    change_type: Literal["planted", "resonating", "harvested"]
    context: Optional[str] = None
    created_at: datetime


class ChapterCharacterStateRow(BaseModel):
    id: int
    project_id: str
    chapter_num: int
    character_id: str
    state_text: Optional[str] = None
    updated_at: datetime

