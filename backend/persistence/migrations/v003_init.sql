-- realtime_novel v003_init.sql
-- 整体重写：DB 底层重构（spec: .spec/db-refactor/spec.md）
-- 背景：历史数据全清，从零设计合理的表结构
-- 重点：消除 metadata_json 黑洞 / 拆 timeline+geography 独立成表 / onboarding_state 重设计

-- ============================================================
-- 0. 迁移日志
-- ============================================================
CREATE TABLE IF NOT EXISTS migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL
);

-- ============================================================
-- 1. 旧表清理（DROP，按依赖逆序）
-- ============================================================

-- 1.1 历史快照表
DROP TABLE IF EXISTS projects_deleted;

-- 1.2 演员模式表（v0.6.2 起废弃）
DROP TABLE IF EXISTS style_charter;

-- 1.3 题材共鸣表（信息并入 world_tree.genre_tags_json）
DROP TABLE IF EXISTS genre_resonance;

-- 1.4 章节相关流水表
DROP TABLE IF EXISTS chapter_seed_changes;
DROP TABLE IF EXISTS chapter_character_states;

-- 1.5 旧主线表（PK = project_id 单行结构，拆解为新 main_plot 1:n 节点表）
DROP TABLE IF EXISTS main_plot;

-- 1.6 sqlite-vec 历史遗留占位
DROP TABLE IF EXISTS world_entries_vec;
DROP TABLE IF EXISTS world_entries_vec_chunks;
DROP TABLE IF EXISTS world_entries_vec_info;
DROP TABLE IF EXISTS world_entries_vec_rowids;
DROP TABLE IF EXISTS world_entries_vec_vector_chunks00;

-- ============================================================
-- 2. 基础设施（conversations / messages / users）
-- ============================================================

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

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    project_id TEXT,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT,
    tool_calls TEXT,
    tool_results TEXT,
    agent_name TEXT,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_msg_conv_time ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_msg_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_msg_project ON messages(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_msg_conv_project ON messages(conversation_id, project_id);
CREATE INDEX IF NOT EXISTS idx_msg_agent ON messages(agent_name, created_at DESC);

CREATE TABLE IF NOT EXISTS tool_calls_log (
    id TEXT PRIMARY KEY,
    message_id TEXT,
    tool_name TEXT NOT NULL,
    args TEXT,
    result TEXT,
    duration_ms INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_tclog_msg ON tool_calls_log(message_id);
CREATE INDEX IF NOT EXISTS idx_tclog_tool ON tool_calls_log(tool_name);
CREATE INDEX IF NOT EXISTS idx_tclog_time ON tool_calls_log(created_at DESC);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (user_id, key)
);

-- ============================================================
-- 3. 项目级（projects + project_state）
-- ============================================================

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    exploration_level TEXT NOT NULL DEFAULT 'standard',
    cover_image_url TEXT,
    style_pack_id TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    deleted_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_deleted ON projects(deleted_at);

-- project_state: 1:1 承载 projects 运行时状态（高频写）
CREATE TABLE project_state (
    project_id TEXT PRIMARY KEY,
    current_pov TEXT,
    current_chapter INTEGER DEFAULT 0,
    current_volume_id TEXT,
    current_timeline_event_id TEXT,
    current_geography_location_ids_json TEXT,
    last_generated_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- ============================================================
-- 4. 世界树基座（world_tree 5 字段最终态）
-- ============================================================

CREATE TABLE world_tree (
    project_id TEXT PRIMARY KEY,
    story_core TEXT,
    genre_tags_json TEXT,
    core_rules_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- ============================================================
-- 5. 世界树基座 · 时间线 / 地理（拆自 world_tree）
-- ============================================================

CREATE TABLE timeline_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    era_name TEXT NOT NULL,
    era_order INTEGER,
    event_name TEXT NOT NULL,
    description TEXT,
    event_order INTEGER,
    start_year TEXT,
    end_year TEXT,
    related_main_plot_node_id TEXT,
    related_char_ids_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (related_main_plot_node_id) REFERENCES main_plot(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_timeline_events_project
    ON timeline_events(project_id, era_order, event_order);

CREATE TABLE geography_locations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'region'
        CHECK(category IN ('realm', 'continent', 'country', 'region', 'city', 'sect', 'landmark', 'other')),
    description TEXT,
    significance TEXT,
    parent_location_id TEXT,
    related_char_ids_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_location_id) REFERENCES geography_locations(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_geography_locations_project ON geography_locations(project_id);
CREATE INDEX IF NOT EXISTS idx_geography_locations_parent ON geography_locations(parent_location_id);

-- ============================================================
-- 6. 世界树基座 · 世界百科（world_entries 通用条目）
-- ============================================================

CREATE TABLE world_entries (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    category TEXT NOT NULL
        CHECK(category IN (
            'magic', 'tech', 'social', 'politics', 'economy',
            'mythology', 'history', 'geography', 'other'
        )),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    related_char_ids_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_world_entries_project ON world_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_world_entries_category ON world_entries(project_id, category);

-- ============================================================
-- 7. 世界树基座 · 角色（characters + character_relationships）
-- ============================================================

CREATE TABLE characters (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('protagonist', 'deuteragonist', 'antagonist', 'supporting', 'minor')),
    traits_json TEXT,
    speech_style TEXT,
    background TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id);
CREATE INDEX IF NOT EXISTS idx_characters_role ON characters(project_id, role);
CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(project_id, name);

-- character_relationships 极简化保留
CREATE TABLE character_relationships (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    char_a_id TEXT NOT NULL,
    char_b_id TEXT NOT NULL,
    rel_type TEXT NOT NULL CHECK(rel_type IN (
        'family', 'lover', 'friend', 'ally', 'rival',
        'enemy', 'mentor', 'subordinate'
    )),
    description TEXT,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE(project_id, char_a_id, char_b_id),
    CHECK(char_a_id < char_b_id),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (char_a_id) REFERENCES characters(id) ON DELETE CASCADE,
    FOREIGN KEY (char_b_id) REFERENCES characters(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_char_rel_project ON character_relationships(project_id);
CREATE INDEX IF NOT EXISTS idx_char_rel_a ON character_relationships(char_a_id);
CREATE INDEX IF NOT EXISTS idx_char_rel_b ON character_relationships(char_b_id);

-- ============================================================
-- 8. 世界树基座 · 卷 / 主线 / 支线（1:n 节点表）
-- ============================================================

CREATE TABLE volumes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    volume_num INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    planned_chapter_count INTEGER,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_volumes_num ON volumes(project_id, volume_num);

CREATE TABLE main_plot (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    volume_id TEXT,
    plot_num INTEGER NOT NULL,
    title TEXT,
    description TEXT NOT NULL,
    estimated_chapter INTEGER,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'active', 'completed')),
    related_char_ids_json TEXT,
    related_timeline_event_id TEXT,
    related_geography_location_ids_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (volume_id) REFERENCES volumes(id) ON DELETE SET NULL,
    FOREIGN KEY (related_timeline_event_id) REFERENCES timeline_events(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_main_plot_project ON main_plot(project_id, plot_num);

CREATE TABLE sub_plot (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    volume_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    chapter_start INTEGER,
    chapter_end INTEGER,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('active', 'pending', 'completed', 'abandoned')),
    priority TEXT NOT NULL DEFAULT 'side'
        CHECK(priority IN ('main', 'side', 'minor')),
    related_char_ids_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (volume_id) REFERENCES volumes(id) ON DELETE SET NULL
);

-- ============================================================
-- 9. 世界树基座 · 伏笔（seeds 合并 seed_states 单表）
-- ============================================================

CREATE TABLE seeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    trigger TEXT,
    payoff TEXT,
    category TEXT NOT NULL DEFAULT 'plot'
        CHECK(category IN ('plot', 'character', 'world', 'minor')),
    scope TEXT NOT NULL DEFAULT 'mid'
        CHECK(scope IN ('long', 'mid', 'short')),
    estimated_plant_chapter INTEGER,
    estimated_payoff_chapter INTEGER,
    related_char_ids_json TEXT,
    related_main_plot_node_id TEXT,
    related_sub_plot_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'planted', 'resonating', 'harvested', 'abandoned')),
    planted_at_chapter INTEGER,
    planted_context TEXT,
    last_seen_chapter INTEGER,
    weight REAL DEFAULT 0.5,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (related_main_plot_node_id) REFERENCES main_plot(id) ON DELETE SET NULL,
    FOREIGN KEY (related_sub_plot_id) REFERENCES sub_plot(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_seeds_project ON seeds(project_id);
CREATE INDEX IF NOT EXISTS idx_seeds_status ON seeds(project_id, status);

-- ============================================================
-- 10. 章节（chapters + chapter_status）
-- ============================================================

CREATE TABLE chapter_status (
    project_id TEXT NOT NULL,
    chapter_num INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('idle', 'generating', 'done', 'failed')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT,
    PRIMARY KEY (project_id, chapter_num)
);
CREATE INDEX IF NOT EXISTS idx_chap_status ON chapter_status(project_id, status);

CREATE TABLE chapters (
    project_id TEXT NOT NULL,
    chapter_num INTEGER NOT NULL,
    volume_id TEXT,
    title TEXT,
    summary TEXT,
    word_count INTEGER DEFAULT 0,
    file_path TEXT NOT NULL,
    intervention TEXT,
    generated_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (project_id, chapter_num),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (volume_id) REFERENCES volumes(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_chapters_project ON chapters(project_id, chapter_num DESC);

-- ============================================================
-- 11. Onboarding 状态（spec §5.8 重设计）
-- ============================================================

CREATE TABLE onboarding_state (
    project_id TEXT PRIMARY KEY,
    info_state TEXT NOT NULL DEFAULT 'collecting'
        CHECK(info_state IN ('collecting', 'wtm_pending', 'ready')),
    payload_json TEXT,
    -- v003: 保留旧字段（arch-plan §6.3 要求不破坏现有代码）
    -- current_step: 旧 step 编号（0-5），OnboardingRepository 写入用
    -- state_json: 旧状态机 JSON，保留为可选
    current_step INTEGER NOT NULL DEFAULT 0,
    state_json TEXT,
    last_activity_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- ============================================================
-- 12. 迁移日志
-- ============================================================
INSERT OR IGNORE INTO migrations (version, applied_at) VALUES ('v003_init', CURRENT_TIMESTAMP);
