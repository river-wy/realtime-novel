"""持久化层 Pydantic Schema"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from typing import Any, Optional, Literal


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


# ============ conversations / messages ============

class Conversation(BaseModel):
    id: str
    user_id: str
    created_at: datetime
    last_active_at: datetime
    status: ConversationStatus = ConversationStatus.ACTIVE
    invalidated_at: Optional[datetime] = None
    summary: Optional[str] = None
    message_count: int = 0


class Message(BaseModel):
    id: str
    conversation_id: str
    project_id: Optional[str] = None
    role: MessageRole
    content: Optional[str] = None
    tool_calls: Optional[dict[str, Any]] = None
    tool_results: Optional[dict[str, Any]] = None
    agent_name: Optional[str] = None   # 处理该消息的 agent：novel_steward / novel_writer / world_tree_manager
    created_at: datetime


class ToolCallLog(BaseModel):
    id: str
    message_id: Optional[str] = None
    tool_name: str
    args: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
    duration_ms: int
    created_at: datetime


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


# ============ projects + 6 件基座 ============

class Project(BaseModel):
    id: str
    name: str
    palette: str = ""
    exploration_level: str = "standard"
    current_pov: Optional[str] = None       # char_id，由 switch_pov 维护
    cover_image_url: Optional[str] = None
    style_pack_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class WorldTreeRow(BaseModel):
    project_id: str
    timeline_era: Optional[str] = None
    anchor_event: Optional[str] = None
    geography_primary: Optional[str] = None
    geography_secondary_json: Optional[str] = None
    geography_spatial_rules_json: Optional[str] = None
    core_rules_json: Optional[str] = None
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
    beats_json: Optional[str] = None
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
    name: Optional[str] = None
    trigger: Optional[str] = None
    payoff: Optional[str] = None
    estimated_chapter: Optional[int] = None
    payoff_chapter: Optional[int] = None
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
    """章节 metadata（正文存文件 data/projects/{id}/chapters/chapter_NNN.md）"""
    project_id: str
    chapter_num: int
    title: Optional[str] = None
    summary: Optional[str] = None
    detailed_summary: Optional[str] = None
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

