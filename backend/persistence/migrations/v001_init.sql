-- realtime_novel 初始 Schema（合并自历史 v001-v007）

-- 1. 迁移日志
CREATE TABLE IF NOT EXISTS migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL
);

-- 2. 对话线程
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_active_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'invalidated', 'archived')),
    invalidated_at TIMESTAMP,
    summary TEXT,
    message_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_last_active ON conversations(last_active_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_status ON conversations(user_id, status);
CREATE INDEX IF NOT EXISTS idx_conv_invalidated ON conversations(invalidated_at DESC);

-- 3. 对话消息
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    project_id TEXT,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT,
    tool_calls TEXT,       -- JSON
    tool_results TEXT,     -- JSON
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_msg_conv_time ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_msg_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_msg_project ON messages(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_msg_conv_project ON messages(conversation_id, project_id);

-- 4. 工具调用审计
CREATE TABLE IF NOT EXISTS tool_calls_log (
    id TEXT PRIMARY KEY,
    message_id TEXT,
    tool_name TEXT NOT NULL,
    args TEXT,             -- JSON
    result TEXT,           -- JSON
    duration_ms INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_tclog_msg ON tool_calls_log(message_id);
CREATE INDEX IF NOT EXISTS idx_tclog_tool ON tool_calls_log(tool_name);
CREATE INDEX IF NOT EXISTS idx_tclog_time ON tool_calls_log(created_at DESC);

-- 5. 用户偏好
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (user_id, key)
);

-- 6. 章节生成状态
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

-- 7. 软删除记录
CREATE TABLE IF NOT EXISTS projects_deleted (
    project_id TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    palette TEXT NOT NULL,
    deleted_at TIMESTAMP NOT NULL,
    trash_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_deleted_at ON projects_deleted(deleted_at DESC);

-- 8. 项目元数据
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    palette TEXT NOT NULL DEFAULT '',
    current_pov TEXT,              -- 当前 POV 角色 char_id（switch_pov 工具维护）
    exploration_level TEXT NOT NULL DEFAULT 'standard',
    cover_image_url TEXT,
    style_pack_id TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    deleted_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_deleted ON projects(deleted_at);

-- 9. 世界树
CREATE TABLE IF NOT EXISTS world_tree (
    project_id TEXT PRIMARY KEY,
    timeline_era TEXT,
    anchor_event TEXT,
    geography_primary TEXT,
    geography_secondary_json TEXT,      -- list[str]
    geography_spatial_rules_json TEXT,  -- list[str]
    core_rules_json TEXT,               -- list[CoreRule] JSON
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 10. 题材共鸣
CREATE TABLE IF NOT EXISTS genre_resonance (
    project_id TEXT PRIMARY KEY,
    accept_json TEXT,    -- list[{text, weight}]
    reject_json TEXT,    -- list[{text, weight}]
    anchors_json TEXT,   -- list[{phrase, sentiment, binding}]
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 11. 主线
CREATE TABLE IF NOT EXISTS main_plot (
    project_id TEXT PRIMARY KEY,
    current_beat INTEGER DEFAULT 0,
    arc_phrase TEXT,
    beats_json TEXT,     -- list[Beat]
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 12. 支线（一对多）
CREATE TABLE IF NOT EXISTS sub_plot (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    parent_beat_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('active', 'pending', 'completed', 'abandoned')),
    priority TEXT NOT NULL CHECK(priority IN ('main', 'side', 'minor')),
    linked_seeds_json TEXT,   -- list[int]
    linked_chars_json TEXT,   -- list[str]
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_subplot_project ON sub_plot(project_id);
CREATE INDEX IF NOT EXISTS idx_subplot_status ON sub_plot(project_id, status);

-- 13. 人物（一对多）
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('protagonist', 'deuteragonist', 'antagonist', 'supporting', 'minor')),
    traits_json TEXT,    -- list[str]
    speech_style TEXT,
    background TEXT,
    arc TEXT,
    internal_state TEXT,
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id);
CREATE INDEX IF NOT EXISTS idx_characters_role ON characters(project_id, role);
CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(project_id, name);

-- 14. 人物关系（一对多）
CREATE TABLE IF NOT EXISTS character_relationships (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    from_char_id TEXT NOT NULL,
    to_char_id TEXT NOT NULL,
    type TEXT,
    description TEXT,
    evolution_json TEXT,  -- list[{chapter, change}]
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (from_char_id) REFERENCES characters(id) ON DELETE CASCADE,
    FOREIGN KEY (to_char_id) REFERENCES characters(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_rel_project ON character_relationships(project_id);
CREATE INDEX IF NOT EXISTS idx_rel_from ON character_relationships(from_char_id);
CREATE INDEX IF NOT EXISTS idx_rel_to ON character_relationships(to_char_id);

-- 15. 伏笔种子（一对多）
CREATE TABLE IF NOT EXISTS seeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    content TEXT NOT NULL,
    name TEXT,
    trigger TEXT,
    payoff TEXT,
    estimated_chapter INTEGER,
    payoff_chapter INTEGER,
    importance_primary TEXT NOT NULL CHECK(importance_primary IN ('主线推进', '支线故事', '小巧思')),
    size TEXT NOT NULL CHECK(size IN ('长线', '中线', '点状')),
    planned_interval INTEGER,
    orientation TEXT NOT NULL CHECK(orientation IN ('剧情翻转', '关键成员关系', '主角成长', '支线揭示', '小巧思', '氛围营造')),
    planted_at_chapter INTEGER DEFAULT 0,
    planted_in_node TEXT,
    planted_context TEXT,
    last_seen_chapter INTEGER DEFAULT 0,
    weight REAL DEFAULT 0.5,
    status TEXT NOT NULL CHECK(status IN ('planted', 'resonating', 'harvested', 'abandoned')),
    linked_char_ids_json TEXT,  -- list[str]
    linked_subplot_id TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_seeds_project ON seeds(project_id);
CREATE INDEX IF NOT EXISTS idx_seeds_status ON seeds(project_id, status);
CREATE INDEX IF NOT EXISTS idx_seeds_planted ON seeds(planted_at_chapter);

-- 16. 章节 metadata（正文存文件 data/projects/{id}/chapters/chapter_NNN.md）
CREATE TABLE IF NOT EXISTS chapters (
    project_id TEXT NOT NULL,
    chapter_num INTEGER NOT NULL,
    title TEXT,
    summary TEXT,
    detailed_summary TEXT,
    word_count INTEGER DEFAULT 0,
    file_path TEXT NOT NULL,
    intervention TEXT,
    actor_feedback TEXT,
    actor_character TEXT,
    generated_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (project_id, chapter_num),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chapters_project ON chapters(project_id, chapter_num DESC);

-- 17. Onboarding 中间态
CREATE TABLE IF NOT EXISTS onboarding_state (
    project_id TEXT PRIMARY KEY,
    current_step INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL,
    state_json TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 18. 章节-种子变化关联
CREATE TABLE IF NOT EXISTS chapter_seed_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_num INTEGER NOT NULL,
    seed_id INTEGER NOT NULL,
    change_type TEXT NOT NULL CHECK(change_type IN ('planted', 'resonating', 'harvested')),
    context TEXT,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id, chapter_num) REFERENCES chapters(project_id, chapter_num) ON DELETE CASCADE,
    FOREIGN KEY (seed_id) REFERENCES seeds(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_seed_changes_chapter ON chapter_seed_changes(project_id, chapter_num);
CREATE INDEX IF NOT EXISTS idx_seed_changes_seed ON chapter_seed_changes(seed_id);

-- 19. 章节-角色状态关联
CREATE TABLE IF NOT EXISTS chapter_character_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_num INTEGER NOT NULL,
    character_id TEXT NOT NULL,
    state_text TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id, chapter_num) REFERENCES chapters(project_id, chapter_num) ON DELETE CASCADE,
    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_char_states_chapter ON chapter_character_states(project_id, chapter_num);
CREATE INDEX IF NOT EXISTS idx_char_states_char ON chapter_character_states(character_id);
