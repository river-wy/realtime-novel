"""backend.persistence 包入口

导出：
- get_store / reset_store: SQLiteStore 全局单例
- ConversationRepository / ToolCallLogRepository / AgentStateRepository
- UserPreferenceRepository / ChapterStatusRepository / ProjectDeletedRepository
- ProjectRepository (v0.4.1 新增)
- ChapterRepository
- OnboardingRepository
"""
from backend.persistence.agent_state_repository import AgentStateRepository
from backend.persistence.chapter_repository import ChapterRepository
from backend.persistence.chapter_status_repository import ChapterStatusRepository
from backend.persistence.conversation_repository import ConversationRepository
from backend.persistence.models import (
    Conversation, Message, MessageRole, ToolCallLog, AgentState,
    UserPreference, ChapterStatus, ChapterState, ProjectDeleted,
    Project, WorldTreeRow, StyleCharterRow, GenreResonanceRow,
    MainPlotRow, SubPlotRow, CharacterRow, CharacterRelationshipRow, SeedRow,
    CharacterRole, SeedStatus, SubplotStatus, SubplotPriority,
    ChapterRow, OnboardingStateRow,
    ChapterSeedChangeRow, ChapterCharacterStateRow,
)
from backend.persistence.onboarding_repository import OnboardingRepository
from backend.persistence.project_deleted_repository import ProjectDeletedRepository
from backend.persistence.project_repository import ProjectRepository
from backend.persistence.sqlite_store import SQLiteStore, get_store, reset_store
from backend.persistence.tool_call_log_repository import ToolCallLogRepository
from backend.persistence.user_preference_repository import UserPreferenceRepository

__all__ = [
    # models
    "Conversation", "Message", "MessageRole", "ToolCallLog", "AgentState",
    "UserPreference", "ChapterStatus", "ChapterState", "ProjectDeleted",
    "Project", "WorldTreeRow", "StyleCharterRow", "GenreResonanceRow",
    "MainPlotRow", "SubPlotRow", "CharacterRow", "CharacterRelationshipRow", "SeedRow",
    "CharacterRole", "SeedStatus", "SubplotStatus", "SubplotPriority",
    "ChapterRow", "OnboardingStateRow",
    "ChapterSeedChangeRow", "ChapterCharacterStateRow",
    # store
    "SQLiteStore", "get_store", "reset_store",
    # repos
    "ConversationRepository", "ToolCallLogRepository", "AgentStateRepository",
    "UserPreferenceRepository", "ChapterStatusRepository", "ProjectDeletedRepository",
    "ProjectRepository", "ChapterRepository", "OnboardingRepository",
]
