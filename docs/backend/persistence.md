# 后端数据存储文档

> **最后更新**：2026-06-29
> **版本**：v0.9.x

---

## 目录

1. [存储策略概览](#1-存储策略概览)
2. [SQLiteStore（连接管理）](#2-sqlitestore)
3. [数据库 Schema（19 张表）](#3-数据库-schema)
4. [Repository 层](#4-repository-层)
5. [章节正文文件存储](#5-章节正文文件存储)
6. [数据迁移机制](#6-数据迁移机制)
7. [软删除与回档](#7-软删除与回档)

---

## 1. 存储策略概览

系统采用 **SQLite + 文件系统** 双存储策略：

| 数据类型 | 存储位置 | 说明 |
|---------|---------|------|
| 项目元数据 | `data/novel.db` | SQLite，结构化查询 |
| 世界树 7 件基座 | `data/novel.db` | SQLite，19 张关联表 |
| 对话历史 | `data/novel.db` | SQLite，消息流水 |
| 工具调用审计 | `data/novel.db` | SQLite，完整链路追踪 |
| 章节正文 | `data/projects/{id}/chapters/chapter_NNN.md` | Markdown 文件 |
| 封面图 | `data/projects/{id}/cover.png` | PNG 文件 |

**选择 SQLite 的原因**：
- 单机部署，无需额外数据库服务
- WAL 模式支持并发读（WS 消息处理期间可并行查询）
- 文件即数据库，备份只需 `cp data/novel.db data/novel.db.bak`

**章节正文存文件的原因**：
- 单章节最大 1-2 万汉字，存 BLOB 不如存 Markdown 文件可读性好
- 方便手动编辑/备份/导出

---

## 2. SQLiteStore

`backend/persistence/sqlite_store.py` 是数据库连接的唯一入口。

### 设计特点

- **WAL 模式**：`PRAGMA journal_mode=WAL`，支持读写并发，避免写操作阻塞查询
- **外键约束**：`PRAGMA foreign_keys=ON`，确保引用完整性
- **Row Factory**：`conn.row_factory = sqlite3.Row`，查询结果可按列名访问
- **全局单例**：`get_store()` 返回单例，进程内共享连接工厂

### 连接接口

```
SQLiteStore.connection() → contextmanager[sqlite3.Connection]
  每次 yield 一个新连接，用完自动关闭
  autocommit 模式（isolation_level=None）

SQLiteStore.transaction() → contextmanager[sqlite3.Connection]
  显式事务：自动 BEGIN/COMMIT/ROLLBACK
  适用于多表写入需要原子性的场景
```

### 使用模式

每个 Repository 通过 `get_store().connection()` 或 `.transaction()` 获取连接：

```
class ProjectRepository:
    def get(self, project_id: str) -> Optional[Project]:
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id=?", (project_id,)
            ).fetchone()
            return Project(**dict(row)) if row else None
```

---

## 3. 数据库 Schema

所有表定义集中在 `backend/persistence/migrations/v001_init.sql`（合并自历史 v001-v007 迁移）。

### 表总览（19 张）

| 序号 | 表名 | 类型 | 说明 |
|------|------|------|------|
| 1 | `migrations` | 系统 | 迁移版本记录 |
| 2 | `conversations` | 对话 | 对话线程 |
| 3 | `messages` | 对话 | 对话消息（含 tool_calls JSON） |
| 4 | `tool_calls_log` | 审计 | 工具调用详细记录 |
| 5 | `user_preferences` | 用户 | 用户偏好（key-value） |
| 6 | `chapter_status` | 章节 | 章节生成状态 |
| 7 | `projects_deleted` | 项目 | 软删除记录 |
| 8 | `projects` | 项目 | 项目元数据 |
| 9 | `world_tree` | 基座 | 世界树设定 |
| 10 | `genre_resonance` | 基座 | 题材共鸣 |
| 11 | `main_plot` | 基座 | 主线 |
| 12 | `sub_plot` | 基座 | 支线（一对多） |
| 13 | `characters` | 基座 | 人物（一对多） |
| 14 | `character_relationships` | 基座 | 人物关系（多对多） |
| 15 | `seeds` | 基座 | 伏笔种子（一对多） |
| 16 | `chapters` | 章节 | 章节 metadata（正文存文件） |
| 17 | `onboarding_state` | 流程 | Onboarding 中间态 |
| 18 | `chapter_seed_changes` | 关联 | 章节-种子变化 |
| 19 | `chapter_character_states` | 关联 | 章节-角色状态快照 |

### 核心表详细设计

#### `projects`（项目元数据）

```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    palette TEXT NOT NULL DEFAULT '',          -- UI 色调标签
    current_pov TEXT,                          -- 当前 POV 角色 char_id
    exploration_level TEXT NOT NULL DEFAULT 'standard',
    cover_image_url TEXT,
    style_pack_id TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    deleted_at TIMESTAMP                       -- 软删除时间戳
);
```

`exploration_level` 约束为：`conservative` / `standard` / `wild`

#### `conversations` + `messages`（对话历史）

```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_active_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'invalidated', 'archived')),
    summary TEXT,                              -- LLM 压缩的历史摘要
    message_count INTEGER DEFAULT 0
);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    project_id TEXT,                           -- 消息关联的项目（可选）
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT,
    tool_calls TEXT,                           -- JSON：LLM 决定调用的工具
    tool_results TEXT,                         -- JSON：工具返回结果
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
```

**对话管理策略**：
- 24h 滑窗：最近活跃对话在 24h 内复用，超时后状态变为 `archived`
- `ConversationRepository.get_or_refresh_active_conversation(user_id)` 自动维护

#### `world_tree`（世界树 - 单行聚合）

```sql
CREATE TABLE world_tree (
    project_id TEXT PRIMARY KEY,
    timeline_era TEXT,
    anchor_event TEXT,
    geography_primary TEXT,
    geography_secondary_json TEXT,      -- list[str]（JSON 编码）
    geography_spatial_rules_json TEXT,  -- list[str]（JSON 编码）
    core_rules_json TEXT,               -- list[CoreRule]（JSON 编码）
    metadata_json TEXT,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
```

**JSON 列约定**：复杂结构（列表/对象）序列化为 JSON 字符串存储，读取时反序列化。

#### `seeds`（伏笔种子）

```sql
CREATE TABLE seeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    content TEXT NOT NULL,
    name TEXT,
    trigger TEXT,                              -- 触发条件
    payoff TEXT,                               -- 收割场景
    estimated_chapter INTEGER,
    payoff_chapter INTEGER,                    -- 实际收割章节
    importance_primary TEXT NOT NULL
        CHECK(importance_primary IN ('主线推进', '支线故事', '小巧思')),
    size TEXT NOT NULL
        CHECK(size IN ('长线', '中线', '点状')),
    planned_interval INTEGER,
    orientation TEXT NOT NULL
        CHECK(orientation IN ('剧情翻转', '关键成员关系', '主角成长', '支线揭示', '小巧思', '氛围营造')),
    planted_at_chapter INTEGER DEFAULT 0,
    last_seen_chapter INTEGER DEFAULT 0,
    weight REAL DEFAULT 0.5,                   -- 调度权重（0.0-1.0）
    status TEXT NOT NULL
        CHECK(status IN ('planted', 'resonating', 'harvested', 'abandoned')),
    ...
);
```

种子状态流转：`planted` → `resonating`（提及但未收割）→ `harvested`（正式收割）/ `abandoned`（废弃）

#### `chapters`（章节 metadata）

```sql
CREATE TABLE chapters (
    project_id TEXT NOT NULL,
    chapter_num INTEGER NOT NULL,
    title TEXT,
    summary TEXT,                              -- 一句话概要（LLM 抽取）
    detailed_summary TEXT,                     -- 详细摘要（未来扩展）
    word_count INTEGER DEFAULT 0,
    file_path TEXT NOT NULL,                   -- 正文文件相对路径
    intervention TEXT,                         -- 生成时的干预指令
    actor_feedback TEXT,
    actor_character TEXT,                      -- 视角角色
    generated_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (project_id, chapter_num),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
```

正文内容不存 DB，`file_path` 指向 `data/projects/{id}/chapters/chapter_NNN.md`。

#### `tool_calls_log`（工具调用审计）

```sql
CREATE TABLE tool_calls_log (
    id TEXT PRIMARY KEY,
    message_id TEXT,                           -- 关联的 assistant message
    tool_name TEXT NOT NULL,
    args TEXT,                                 -- JSON
    result TEXT,                               -- JSON
    duration_ms INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
);
```

完整记录每次工具调用的输入/输出/耗时，便于调试和回溯。

### 索引设计

所有常用查询路径都有索引：

```sql
-- 对话：按用户 + 状态查最近对话
CREATE INDEX idx_conv_user ON conversations(user_id);
CREATE INDEX idx_conv_status ON conversations(user_id, status);
CREATE INDEX idx_conv_last_active ON conversations(last_active_at DESC);

-- 消息：按对话时间顺序
CREATE INDEX idx_msg_conv_time ON messages(conversation_id, created_at);
-- 消息：按项目查
CREATE INDEX idx_msg_project ON messages(project_id, created_at DESC);

-- 章节：按项目倒序
CREATE INDEX idx_chapters_project ON chapters(project_id, chapter_num DESC);

-- 种子：按状态
CREATE INDEX idx_seeds_status ON seeds(project_id, status);

-- 人物：按角色
CREATE INDEX idx_characters_role ON characters(project_id, role);
```

---

## 4. Repository 层

每张（组）表对应一个 Repository，提供类型安全的 CRUD 接口。

### 各 Repository 职责

| Repository | 文件 | 管理的表 |
|-----------|------|---------|
| `ProjectRepository` | `project_repository.py` | projects + world_tree + genre_resonance + main_plot + sub_plot + characters + character_relationships + seeds |
| `ChapterRepository` | `chapter_repository.py` | chapters（metadata）+ 文件读写 |
| `ConversationRepository` | `conversation_repository.py` | conversations + messages |
| `OnboardingRepository` | `onboarding_repository.py` | onboarding_state |
| `ChapterStatusRepository` | `chapter_status_repository.py` | chapter_status |
| `ToolCallLogRepository` | `tool_call_log_repository.py` | tool_calls_log |
| `ProjectDeletedRepository` | `project_deleted_repository.py` | projects_deleted |
| `UserPreferenceRepository` | `user_preference_repository.py` | user_preferences |

### Pydantic Row Model（`persistence/models.py`）

所有 DB 行数据都映射为 Pydantic `BaseModel`，提供类型检查和序列化：

```
Project, WorldTreeRow, GenreResonanceRow, MainPlotRow,
SubPlotRow, CharacterRow, CharacterRelationshipRow, SeedRow,
ChapterRow, ConversationStatus, Message, ToolCallLog,
UserPreference, ChapterStatus, ProjectDeleted, OnboardingStateRow,
ChapterSeedChangeRow, ChapterCharacterStateRow
```

**Enum 类型**：

| Enum | 取值 |
|------|------|
| `MessageRole` | user / assistant / system / tool |
| `ChapterState` | idle / generating / done / failed |
| `ConversationStatus` | active / invalidated / archived |
| `CharacterRole` | protagonist / deuteragonist / antagonist / supporting / minor |
| `SeedStatus` | planted / resonating / harvested / abandoned |
| `SubplotStatus` | active / pending / completed / abandoned |
| `SubplotPriority` | main / side / minor |

### ProjectRepository（最复杂的 Repository）

`ProjectRepository` 同时管理项目 + 7 件基座，提供：

- `create(project_id, name, palette)` → 创建项目 + 初始化 7 件基座空行
- `get(project_id)` → 查项目元数据
- `get_full(project_id)` → 查项目 + 全量 7 件基座
- `update_world_tree(project_id, data)` → 更新世界树字段
- `update_characters(project_id, chars)` → 批量替换角色
- `add_seed(project_id, seed_data)` → 新增种子
- `update_seed_status(seed_id, status)` → 更新种子状态
- `soft_delete(project_id)` → 设置 `deleted_at`

### ConversationRepository（对话管理）

核心方法：

- `get_or_refresh_active_conversation(user_id)` → 24h 滑窗，自动创建/复用/归档
- `add_message(conv_id, role, content, ...)` → 追加消息
- `get_recent_messages(conv_id, limit)` → 查最近 N 条消息（分层加载）

---

## 5. 章节正文文件存储

### 目录结构

```
data/projects/
└── {project_id}/
    ├── chapters/
    │   ├── chapter_001.md
    │   ├── chapter_002.md
    │   └── chapter_NNN.md
    └── cover.png
```

### 文件命名规则

- 章节正文：`chapter_{num:03d}.md`（3 位补零）
- 封面图：`cover.png`（固定名，生成覆盖）

### 读写接口

`ChapterRepository` 封装文件操作：

```
write_chapter_file(project_id, chapter_num, content: str) → str (file_path)
read_chapter_file(project_id, chapter_num) → Optional[str]
delete_chapter_file(project_id, chapter_num) → bool
```

正文 Markdown 格式约定：

```markdown
# 第 N 章 章节标题

章节正文内容...
```

### 静态文件服务

封面图通过 FastAPI 静态文件服务对外暴露：

```
GET /static/projects/{project_id}/cover.png
→ data/projects/{project_id}/cover.png
```

URL 存入 `projects.cover_image_url` 字段，前端直接引用。

---

## 6. 数据迁移机制

`SQLiteStore._init_schema()` 在每次应用启动时自动执行未应用的迁移。

### 迁移文件规则

```
backend/persistence/migrations/
└── v001_init.sql    # 当前唯一迁移文件（合并版）
```

- 文件命名：`v{NNN}_{description}.sql`
- 按文件名字母序执行
- 幂等：已执行的版本跳过（记录在 `migrations` 表）
- 容错：`duplicate column` / `already exists` 错误静默跳过（保证重复执行安全）

### 新增迁移

1. 新建 `backend/persistence/migrations/v002_description.sql`
2. 编写 `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS` 语句（确保幂等）
3. 下次启动自动执行

```sql
-- 示例：v002_add_field.sql
ALTER TABLE projects ADD COLUMN word_count INTEGER DEFAULT 0;
```

---

## 7. 软删除与回档

### 软删除（`ProjectManager.soft_delete`）

```
1. projects.deleted_at = NOW()
2. 把项目目录移到 data/projects/.trash/{project_id}-{timestamp}/
3. 写入 projects_deleted 表（原名称/palette/删除时间/trash路径）
```

`GET /api/projects` 默认过滤 `deleted_at IS NOT NULL`，被删项目不展示。

`.trash/` 目录下的数据保留，可手动恢复（未来可实现回收站功能）。

### 回档（`ProjectManager.rollback`）

```
回档到第 N 章：
1. 查 chapters 表，找到所有 chapter_num > N 的章节
2. 逐个删除章节文件（chapter_NNN.md）
3. 从 chapters 表删除对应记录
4. 清理关联的 chapter_seed_changes + chapter_character_states
5. 更新 chapter_status 表（移除被删章节的状态记录）
```

**不可逆操作**：回档后后续章节永久删除，执行前 API 要求 `confirm=true` 参数。

前端展示确认弹窗（`⚠️ 确认回档到第 N 章？后续章节将永久删除`）后才发请求。

