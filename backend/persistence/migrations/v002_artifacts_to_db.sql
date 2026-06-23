-- realtime_novel v0.4.1: 7 件基座文件→DB 迁移
-- 生成日期：2026-06-18 蕾姆酱
-- 背景：v0.4 把 7 件基座存为 YAML 文件（不可靠），v0.4.1 全部入 DB
-- 章节正文仍保留文件（`data/{project_id}/chapters/chapter_NNN.md`）
-- 章节 metadata 入 `chapters` 表

-- 1. projects 表（v0.4 没有，靠文件系统 dataclass，v0.4.1 落 DB）
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,                    -- 项目 ID
    name TEXT NOT NULL,                     -- 项目名
    palette TEXT NOT NULL DEFAULT '',       -- 调色板
    current_pov TEXT,                       -- 当前 POV 角色（switch_pov 工具维护）
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    deleted_at TIMESTAMP                    -- 软删除标记（v0.4 已有 projects_deleted 表）
);
CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_deleted ON projects(deleted_at);

-- 2. world_tree（01-world-tree.yaml → DB）
-- 结构：base: {timeline, geography, core_rules[]} + branches[] + metadata
CREATE TABLE IF NOT EXISTS world_tree (
    project_id TEXT PRIMARY KEY,
    timeline_era TEXT,                      -- Era enum: 现代/古代/未来/架空
    year_range_start INTEGER,               -- {start, end?}
    year_range_end INTEGER,
    anchor_event TEXT,
    geography_primary TEXT,
    geography_secondary_json TEXT,          -- list[str]
    geography_spatial_rules_json TEXT,      -- list[str]
    core_rules_json TEXT,                   -- list[CoreRule] JSON
    branches_json TEXT,                     -- list[TreeNode] JSON
    metadata_json TEXT,                     -- metadata 字段
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 3. style_charter（02-style-charter.yaml → DB）
CREATE TABLE IF NOT EXISTS style_charter (
    project_id TEXT PRIMARY KEY,
    prose_style_json TEXT,                  -- {primary, sentence_length, paragraph_style}
    tone_json TEXT,                         -- {primary, secondary, psychological_per_paragraph}
    density_json TEXT,                      -- {specificity, subjectivity, density, ...}
    taboos_json TEXT,                       -- list[Taboo]
    notes_json TEXT,                        -- list[str] (adjust_style 追加)
    limits_json TEXT,                       -- {psychological_per_paragraph, ...}
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 4. genre_resonance（03-genre-resonance.yaml → DB）
CREATE TABLE IF NOT EXISTS genre_resonance (
    project_id TEXT PRIMARY KEY,
    accept_json TEXT,                       -- list[{text, weight}]
    reject_json TEXT,                       -- list[{text, weight}]
    anchors_json TEXT,                      -- list[{phrase, sentiment, binding}]
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 5. main_plot（04-main-plot.yaml → DB）
CREATE TABLE IF NOT EXISTS main_plot (
    project_id TEXT PRIMARY KEY,
    current_beat INTEGER DEFAULT 0,
    arc_phrase TEXT,
    beats_json TEXT,                        -- list[Beat]
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 6. sub_plot（05-sub-plot.yaml → DB）
-- 一对多：一个 project 多个 subplot
CREATE TABLE IF NOT EXISTS sub_plot (
    id TEXT PRIMARY KEY,                    -- subplot ID
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    parent_beat_id TEXT,                    -- 关联 main_plot.beats.id
    status TEXT NOT NULL CHECK(status IN ('active', 'pending', 'completed', 'abandoned')),
    priority TEXT NOT NULL CHECK(priority IN ('main', 'side', 'minor')),
    linked_seeds_json TEXT,                 -- list[int]
    linked_chars_json TEXT,                 -- list[str]
    beats_json TEXT,                        -- subplot 内 beats
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_subplot_project ON sub_plot(project_id);
CREATE INDEX IF NOT EXISTS idx_subplot_status ON sub_plot(project_id, status);

-- 7. characters（06-character-card.yaml → DB）
-- 一对多：一个 project 多个 character
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,                    -- character ID
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('protagonist', 'deuteragonist', 'antagonist', 'supporting', 'minor')),
    traits_json TEXT,                       -- list[str]
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

-- 8. character_relationships（06-character-card.yaml.relationships → DB）
CREATE TABLE IF NOT EXISTS character_relationships (
    id TEXT PRIMARY KEY,                    -- relationship ID
    project_id TEXT NOT NULL,
    from_char_id TEXT NOT NULL,
    to_char_id TEXT NOT NULL,
    type TEXT,                              -- 关系类型：夫妻/兄妹/师徒/敌对...
    description TEXT,
    evolution_json TEXT,                    -- list[{chapter, change}]
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (from_char_id) REFERENCES characters(id) ON DELETE CASCADE,
    FOREIGN KEY (to_char_id) REFERENCES characters(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_rel_project ON character_relationships(project_id);
CREATE INDEX IF NOT EXISTS idx_rel_from ON character_relationships(from_char_id);
CREATE INDEX IF NOT EXISTS idx_rel_to ON character_relationships(to_char_id);

-- 9. seeds（07-seed-table.yaml → DB）
CREATE TABLE IF NOT EXISTS seeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,   -- seed ID（数字 ID，跨项目可能重复）
    project_id TEXT NOT NULL,
    content TEXT NOT NULL,
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
    linked_char_ids_json TEXT,              -- list[str]
    linked_subplot_id TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_seeds_project ON seeds(project_id);
CREATE INDEX IF NOT EXISTS idx_seeds_status ON seeds(project_id, status);
CREATE INDEX IF NOT EXISTS idx_seeds_planted ON seeds(planted_at_chapter);

-- 10. chapters（章节 metadata 入 DB，正文留文件）
-- v001 已有 chapter_status 表（运行状态），v002 加 chapters 表（持久化 metadata）
CREATE TABLE IF NOT EXISTS chapters (
    project_id TEXT NOT NULL,
    chapter_num INTEGER NOT NULL,
    title TEXT,
    summary TEXT,                           -- 1 句话 summary（v0.5 LLM 同步生成）
    detailed_summary TEXT,                  -- 100-200 字 detailed_summary（v0.5 每 20 章异步生成）
    word_count INTEGER DEFAULT 0,
    file_path TEXT NOT NULL,                -- data/{project_id}/chapters/chapter_NNN.md
    intervention TEXT,                      -- 本章剧情干预
    actor_feedback TEXT,                    -- 演员模式用户反馈
    actor_character TEXT,                   -- 演员模式角色
    generated_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (project_id, chapter_num),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chapters_project ON chapters(project_id, chapter_num DESC);

-- 11. onboarding_state（onboarding 中间态入 DB）
-- v0.4 是 .onboarding-state.json 文件，v0.4.1 入 DB
CREATE TABLE IF NOT EXISTS onboarding_state (
    project_id TEXT PRIMARY KEY,
    current_step INTEGER NOT NULL DEFAULT 0,    -- 0-5
    started_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL,
    state_json TEXT NOT NULL,                   -- OnboardingState 全部字段
    artifacts_generated BOOLEAN DEFAULT 0,
    chapter_1_generated BOOLEAN DEFAULT 0,
    chapter_1_path TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 12. chapter_seed_changes（章节-种子变化，关联表，给 detailed_summary 用）
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

-- 13. chapter_character_states（章节-角色状态，关联表）
CREATE TABLE IF NOT EXISTS chapter_character_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_num INTEGER NOT NULL,
    character_id TEXT NOT NULL,
    state_text TEXT,                         -- 角色在本章结尾的状态
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id, chapter_num) REFERENCES chapters(project_id, chapter_num) ON DELETE CASCADE,
    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_char_states_chapter ON chapter_character_states(project_id, chapter_num);
CREATE INDEX IF NOT EXISTS idx_char_states_char ON chapter_character_states(character_id);
