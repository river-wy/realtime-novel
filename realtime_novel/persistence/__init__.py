"""realtime_novel.persistence 包入口

导出：
- get_store / reset_store: SQLiteStore 全局单例
- ConversationRepository / ToolCallLogRepository / AgentStateRepository
- UserPreferenceRepository / ChapterStatusRepository / ProjectDeletedRepository
- ProjectRepository (v0.4.1 新增)
"""
from realtime_novel.persistence.models import (
    Conversation, Message, MessageRole, ToolCallLog, AgentState,
    UserPreference, ChapterStatus, ChapterState, ProjectDeleted,
    Project, WorldTreeRow, StyleCharterRow, GenreResonanceRow,
    MainPlotRow, SubPlotRow, CharacterRow, CharacterRelationshipRow, SeedRow,
    CharacterRole, SeedStatus, SubplotStatus, SubplotPriority,
    ChapterRow, OnboardingStateRow,
    ChapterSeedChangeRow, ChapterCharacterStateRow,
)
from realtime_novel.persistence.sqlite_store import SQLiteStore, get_store, reset_store
from realtime_novel.persistence.conversation_store import ConversationRepository
from realtime_novel.persistence.tool_call_log import ToolCallLogRepository
from realtime_novel.persistence.agent_state_store import AgentStateRepository
from realtime_novel.persistence.user_preference_store import UserPreferenceRepository
from realtime_novel.persistence.chapter_status_store import (
    ChapterStatusRepository, ProjectDeletedRepository,
)
from realtime_novel.persistence.project_repository import ProjectRepository
from realtime_novel.persistence.chapter_repository import ChapterRepository

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
