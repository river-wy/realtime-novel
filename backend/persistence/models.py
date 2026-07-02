"""持久化层 Pydantic Schema

v003 重构（spec: .spec/db-refactor/spec.md）
- 删除：projects.palette / projects.current_pov → 迁入 project_state
- 删除：world_tree.timeline_era / anchor_event / geography_* / metadata_json → 拆入 timeline_events / geography_locations
- 删除：characters.arc / internal_state / metadata_json
- 删除：seeds.importance_primary / size / orientation / planned_interval / linked_subplot_id
- 删除：character_relationships.evolution_json / metadata_json
- 删除：chapters.detailed_summary / actor_feedback / actor_character
- 删除：旧 main_plot（PK=project_id 单行结构）→ 改 1:n 节点表
- 删除：genre_resonance / projects_deleted / style_charter / chapter_seed_changes / chapter_character_states
- 新增：project_state / volumes / main_plot（1:n）/ world_entries / timeline_events / geography_locations
"""
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


class CharacterRelationshipType(str, Enum):
    FAMILY = "family"
    LOVER = "lover"
    FRIEND = "friend"
    ALLY = "ally"
    RIVAL = "rival"
    ENEMY = "enemy"
    MENTOR = "mentor"
    SUBORDINATE = "subordinate"


class SeedStatus(str, Enum):
    PENDING = "pending"
    PLANTED = "planted"
    RESONATING = "resonating"
    HARVESTED = "harvested"
    ABANDONED = "abandoned"


class SeedCategory(str, Enum):
    PLOT = "plot"
    CHARACTER = "character"
    WORLD = "world"
    MINOR = "minor"


class SeedScope(str, Enum):
    LONG = "long"
    MID = "mid"
    SHORT = "short"


class MainPlotStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"


class SubplotStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class VolumeStatus(str, Enum):
    """v004 新增：卷状态（欧尼酱 20:16 拍板）

    in_progress: 卷进行中（默认）
    completed:   卷已完结（summary 必填）
    """
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class SubplotPriority(str, Enum):
    MAIN = "main"
    SIDE = "side"
    MINOR = "minor"


class GeographyCategory(str, Enum):
    REALM = "realm"
    CONTINENT = "continent"
    COUNTRY = "country"
    REGION = "region"
    CITY = "city"
    SECT = "sect"
    LANDMARK = "landmark"
    OTHER = "other"


class WorldEntryCategory(str, Enum):
    MAGIC = "magic"
    TECH = "tech"
    SOCIAL = "social"
    POLITICS = "politics"
    ECONOMY = "economy"
    MYTHOLOGY = "mythology"
    HISTORY = "history"
    GEOGRAPHY = "geography"
    OTHER = "other"


class OnboardingInfoState(str, Enum):
    COLLECTING = "collecting"
    WTM_PENDING = "wtm_pending"
    READY = "ready"


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
    agent_name: Optional[str] = None
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


# ============ projects + project_state ============

class Project(BaseModel):
    """项目元信息（低频写）"""
    id: str
    name: str
    exploration_level: str = "standard"
    cover_image_url: Optional[str] = None
    style_pack_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class ProjectState(BaseModel):
    """项目运行时状态（高频写，1:1）"""
    project_id: str
    current_pov: Optional[str] = None
    current_chapter: int = 0
    current_volume_id: Optional[str] = None
    current_timeline_event_id: Optional[str] = None
    current_geography_location_ids_json: Optional[str] = None
    last_generated_at: Optional[datetime] = None
    updated_at: datetime


# ============ 世界树基座 ============

class WorldTreeRow(BaseModel):
    """世界树（5 字段最终态）"""
    project_id: str
    story_core: Optional[str] = None
    genre_tags_json: Optional[str] = None
    core_rules_json: Optional[str] = None
    updated_at: datetime


class TimelineEventRow(BaseModel):
    """时间线事件（拆自 world_tree）"""
    id: str
    project_id: str
    era_name: str
    era_order: Optional[int] = None
    event_name: str
    description: Optional[str] = None
    event_order: Optional[int] = None
    start_year: Optional[str] = None  # TEXT：支持"男主 15 岁那年"
    end_year: Optional[str] = None
    related_main_plot_node_id: Optional[str] = None
    related_char_ids_json: Optional[str] = None
    updated_at: datetime


class GeographyLocationRow(BaseModel):
    """地理场景（拆自 world_tree，支持嵌套）"""
    id: str
    project_id: str
    name: str
    category: GeographyCategory = GeographyCategory.REGION
    description: Optional[str] = None
    significance: Optional[str] = None
    parent_location_id: Optional[str] = None
    related_char_ids_json: Optional[str] = None
    updated_at: datetime


class WorldEntryRow(BaseModel):
    """世界百科条目（world_entries）"""
    id: str
    project_id: str
    category: WorldEntryCategory
    title: str
    content: str
    related_char_ids_json: Optional[str] = None
    updated_at: datetime


# ============ 角色 + 关系 ============

class CharacterRow(BaseModel):
    """角色（精简：删 arc / internal_state / metadata_json）"""
    id: str
    project_id: str
    name: str
    role: CharacterRole
    traits_json: Optional[str] = None
    speech_style: Optional[str] = None
    background: Optional[str] = None
    updated_at: datetime


class CharacterRelationshipRow(BaseModel):
    """角色关系（极简化保留，删 evolution_json / metadata_json）"""
    id: str
    project_id: str
    char_a_id: str
    char_b_id: str
    rel_type: CharacterRelationshipType
    description: Optional[str] = None
    updated_at: datetime


# ============ 卷 / 主线 / 支线 ============

class VolumeRow(BaseModel):
    """卷（1:n）

    v004 增强（欧尼酱 20:16 拍板）：
    - status: 卷是否已完结（in_progress / completed）
    - summary: 整卷 1000 字总结，卷完结时由 generate_volume_summary 写入
    """
    id: str
    project_id: str
    volume_num: int
    title: str
    description: Optional[str] = None
    planned_chapter_count: Optional[int] = None
    status: VolumeStatus = VolumeStatus.IN_PROGRESS
    summary: Optional[str] = None
    updated_at: datetime


class MainPlotNodeRow(BaseModel):
    """主线节点（1:n，从旧 beats_json 拆出）"""
    id: str
    project_id: str
    volume_id: Optional[str] = None
    plot_num: int
    title: Optional[str] = None
    description: str
    estimated_chapter: Optional[int] = None
    status: MainPlotStatus = MainPlotStatus.PENDING
    related_char_ids_json: Optional[str] = None
    related_timeline_event_id: Optional[str] = None
    related_geography_location_ids_json: Optional[str] = None
    updated_at: datetime


class SubPlotRow(BaseModel):
    """支线（1:n，字段精简：删 parent_beat_id / metadata_json / linked_seeds_json / linked_chars_json）"""
    id: str
    project_id: str
    volume_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    chapter_start: Optional[int] = None
    chapter_end: Optional[int] = None
    status: SubplotStatus = SubplotStatus.PENDING
    priority: SubplotPriority = SubplotPriority.SIDE
    related_char_ids_json: Optional[str] = None
    updated_at: datetime


# ============ 伏笔（seeds 合并 seed_states 单表） ============

class SeedRow(BaseModel):
    """伏笔（定义 + 运行时状态合并到单表）"""
    id: int
    project_id: str
    name: str
    content: str
    trigger: Optional[str] = None
    payoff: Optional[str] = None
    category: SeedCategory = SeedCategory.PLOT
    scope: SeedScope = SeedScope.MID
    estimated_plant_chapter: Optional[int] = None
    estimated_payoff_chapter: Optional[int] = None
    related_char_ids_json: Optional[str] = None
    related_main_plot_node_id: Optional[str] = None
    related_sub_plot_id: Optional[str] = None
    status: SeedStatus = SeedStatus.PENDING
    planted_at_chapter: Optional[int] = None
    planted_context: Optional[str] = None
    last_seen_chapter: Optional[int] = None
    weight: float = 0.5
    updated_at: datetime


# ============ 章节 ============

class ChapterRow(BaseModel):
    """章节 metadata（正文存文件）

    v003：删 actor_feedback / actor_character / detailed_summary
    """
    project_id: str
    chapter_num: int
    volume_id: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    word_count: int = 0
    file_path: str
    intervention: Optional[str] = None
    generated_at: datetime
    updated_at: datetime


# ============ Onboarding 状态 ============

class OnboardingStateRow(BaseModel):
    """Onboarding 状态（v003 重设计：info_state 三态）

    字段映射：
    - current_step 保留（向后兼容，不依赖）
    - info_state 新增（collecting / wtm_pending / ready）
    - payload_json 替代旧 state_json（管家调工具暂存的信息）
    """
    project_id: str
    info_state: OnboardingInfoState = OnboardingInfoState.COLLECTING
    payload_json: Optional[str] = None
    last_activity_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # 兼容旧字段
    current_step: int = 0
    state_json: Optional[str] = None
