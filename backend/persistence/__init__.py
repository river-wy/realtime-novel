"""backend.persistence 包入口

导出：
- get_store / reset_store: SQLiteStore 全局单例
- ConversationRepository / ToolCallLogRepository / AgentStateRepository
- UserPreferenceRepository / ChapterStatusRepository / ProjectDeletedRepository
- ProjectRepository (v0.4.1 新增)
"""
from backend.persistence.models import (
    Conversation, Message, MessageRole, ToolCallLog, AgentState,
    UserPreference, ChapterStatus, ChapterState, ProjectDeleted,
    Project, WorldTreeRow, StyleCharterRow, GenreResonanceRow,
    MainPlotRow, SubPlotRow, CharacterRow, CharacterRelationshipRow, SeedRow,
    CharacterRole, SeedStatus, SubplotStatus, SubplotPriority,
    ChapterRow, OnboardingStateRow,
    ChapterSeedChangeRow, ChapterCharacterStateRow,
)
from backend.persistence.sqlite_store import SQLiteStore, get_store, reset_store
from backend.persistence.conversation_store import ConversationRepository
from backend.persistence.tool_call_log import ToolCallLogRepository
from backend.persistence.agent_state_store import AgentStateRepository
from backend.persistence.user_preference_store import UserPreferenceRepository
from backend.persistence.chapter_status_store import (
    ChapterStatusRepository, ProjectDeletedRepository,
)
from backend.persistence.project_repository import ProjectRepository
from backend.persistence.chapter_repository import ChapterRepository

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
    "ProjectRepository", "ChapterRepository",
]
