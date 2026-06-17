"""realtime_novel.persistence 包入口

导出：
- get_store / reset_store: SQLiteStore 全局单例
- ConversationRepository / ToolCallLogRepository / AgentStateRepository
- UserPreferenceRepository / ChapterStatusRepository / ProjectDeletedRepository
"""
from realtime_novel.persistence.models import (
    Conversation, Message, MessageRole, ToolCallLog, AgentState,
    UserPreference, ChapterStatus, ChapterState, ProjectDeleted,
)
from realtime_novel.persistence.sqlite_store import SQLiteStore, get_store, reset_store
from realtime_novel.persistence.conversation_store import ConversationRepository
from realtime_novel.persistence.tool_call_log import ToolCallLogRepository
from realtime_novel.persistence.agent_state_store import AgentStateRepository
from realtime_novel.persistence.user_preference_store import UserPreferenceRepository
from realtime_novel.persistence.chapter_status_store import (
    ChapterStatusRepository, ProjectDeletedRepository,
)

__all__ = [
    # models
    "Conversation", "Message", "MessageRole", "ToolCallLog", "AgentState",
    "UserPreference", "ChapterStatus", "ChapterState", "ProjectDeleted",
    # store
    "SQLiteStore", "get_store", "reset_store",
    # repos
    "ConversationRepository", "ToolCallLogRepository", "AgentStateRepository",
    "UserPreferenceRepository", "ChapterStatusRepository", "ProjectDeletedRepository",
]
