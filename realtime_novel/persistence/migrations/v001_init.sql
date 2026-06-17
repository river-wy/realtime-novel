-- realtime_novel v0.4 新增 5 张表 + chapter_status + migrations + sqlite-vec
-- 生成日期：2026-06-17 15:00 蕾姆酱
-- 配套 spec: .spec/m-v0.4/spec.md §4.1

-- 1. 对话线程
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,                    -- uuid
    project_id TEXT,                        -- nullable, 关联 projects/
    user_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_active_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_project ON conversations(project_id);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_last_active ON conversations(last_active_at DESC);

-- 2. 对话消息
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT,
    tool_calls TEXT,                        -- JSON, assistant 角色
    tool_results TEXT,                      -- JSON, tool 角色
    thinking TEXT,                          -- JSON, assistant 角色, LangGraph 中间态
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_msg_conv_time ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_msg_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_msg_content ON messages(content);  -- LIKE 搜索

-- 3. 工具调用审计
CREATE TABLE IF NOT EXISTS tool_calls_log (
    id TEXT PRIMARY KEY,
    message_id TEXT,
    tool_name TEXT NOT NULL,
    args TEXT,                              -- JSON
    result TEXT,                            -- JSON
    duration_ms INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_tclog_msg ON tool_calls_log(message_id);
CREATE INDEX IF NOT EXISTS idx_tclog_tool ON tool_calls_log(tool_name);
CREATE INDEX IF NOT EXISTS idx_tclog_time ON tool_calls_log(created_at DESC);

-- 4. LangGraph checkpoint
CREATE TABLE IF NOT EXISTS agent_state (
    thread_id TEXT PRIMARY KEY,
    checkpoint_data TEXT NOT NULL,          -- JSON
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_state_updated ON agent_state(updated_at DESC);

-- 5. 用户偏好
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (user_id, key)
);

-- 6. 章节状态（v0.4 从 chapter_NNN_status.json 迁入）
CREATE TABLE IF NOT EXISTS chapter_status (
    project_id TEXT NOT NULL,
    chapter_num INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('idle', 'generating', 'done', 'failed')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT,
    PRIMARY KEY (project_id, chapter_num)
);
CREATE INDEX IF NOT EXISTS idx_chap_status ON chapter_status(project_id, status);

-- 7. 迁移日志（必备，避免重复跑）
CREATE TABLE IF NOT EXISTS migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL
);

-- 8. 软删除项目表（v1.3 软删方案 b）
CREATE TABLE IF NOT EXISTS projects_deleted (
    project_id TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    palette TEXT NOT NULL,
    deleted_at TIMESTAMP NOT NULL,
    trash_path TEXT,                        -- data/.trash/{id}-{ts}/
    seven_artifacts_yaml TEXT,              -- 软删时存快照（可选）
    world_tree_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_deleted_at ON projects_deleted(deleted_at DESC);

-- 9. sqlite-vec 向量表（世界书条目）
CREATE VIRTUAL TABLE IF NOT EXISTS world_entries_vec USING vec0(
    entry_id TEXT PRIMARY KEY,
    embedding FLOAT[1536]                   -- 维度待定，假设 1536
);
