"""backend.persistence 包入口

v003 重构：
- 删 ProjectDeleted / GenreResonanceRow / MainPlotRow（旧 PK=project_id 结构）
- 删 ChapterSeedChangeRow / ChapterCharacterStateRow
- 删 ProjectDeletedRepository
- 删 GenreResonance / projects_deleted / style_charter / chapter_seed_changes / chapter_character_states 表
- 新增 MainPlotNodeRow（1:n 节点表）
"""
from backend.persistence.chapter_repository import ChapterRepository
from backend.persistence.chapter_status_repository import ChapterStatusRepository
from backend.persistence.conversation_repository import ConversationRepository
from backend.persistence.models import (
    Conversation, Message, MessageRole, ToolCallLog,
    UserPreference, ChapterStatus, ChapterState,
    Project, ProjectState, WorldTreeRow,
    VolumeRow, MainPlotNodeRow, SubPlotRow,
    CharacterRow, CharacterRelationshipRow, SeedRow,
    TimelineEventRow, GeographyLocationRow, WorldEntryRow,
    CharacterRole, CharacterRelationshipType,
    SeedStatus, SeedCategory, SeedScope,
    SubplotStatus, SubplotPriority, MainPlotStatus,
    GeographyCategory, WorldEntryCategory, OnboardingInfoState,
    ChapterRow, OnboardingStateRow,
)
from backend.persistence.onboarding_repository import OnboardingRepository
from backend.persistence.project_repository import ProjectRepository
from backend.persistence.sqlite_store import SQLiteStore, get_store, reset_store
from backend.persistence.tool_call_log_repository import ToolCallLogRepository
from backend.persistence.user_preference_repository import UserPreferenceRepository

__all__ = [
    # models
    "Conversation", "Message", "MessageRole", "ToolCallLog",
    "UserPreference", "ChapterStatus", "ChapterState",
    "Project", "ProjectState", "WorldTreeRow",
    "VolumeRow", "MainPlotNodeRow", "SubPlotRow",
    "CharacterRow", "CharacterRelationshipRow", "SeedRow",
    "TimelineEventRow", "GeographyLocationRow", "WorldEntryRow",
    "CharacterRole", "CharacterRelationshipType",
    "SeedStatus", "SeedCategory", "SeedScope",
    "SubplotStatus", "SubplotPriority", "MainPlotStatus",
    "GeographyCategory", "WorldEntryCategory", "OnboardingInfoState",
    "ChapterRow", "OnboardingStateRow",
    # store
    "SQLiteStore", "get_store", "reset_store",
    # repos
    "ConversationRepository", "ToolCallLogRepository",
    "UserPreferenceRepository", "ChapterStatusRepository",
    "ProjectRepository", "ChapterRepository", "OnboardingRepository",
]
