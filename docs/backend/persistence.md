# 后端数据存储文档

> **更新日期**：2026-07-02
> **版本**：v0.9.6
> **Commit**：e717e5b
> **代码定位**：`backend/persistence/`

---

## 目录

1. [存储策略概览](#1-存储策略概览)
2. [SQLiteStore（连接管理）](#2-sqlitestore)
3. [数据库 Schema（19 张表）](#3-数据库-schema)
4. [Repository 层（9 个）](#4-repository-层)
5. [章节正文文件存储](#5-章节正文文件存储)
6. [数据迁移机制](#6-数据迁移机制)
7. [软删除与回档](#7-软删除与回档)

---

## 1. 存储策略概览

系统采用 **SQLite + 文件系统** 双存储策略：

| 数据类型 | 存储位置 | 形态 |
|---------|---------|------|
| 项目元数据 | `data/novel.db` | SQLite `projects` / `project_state` |
| 世界树 7 件基座 | `data/novel.db` | SQLite 11 张关联表 |
| 对话历史 | `data/novel.db` | SQLite `conversations` / `messages` |
| 工具调用审计 | `data/novel.db` | SQLite `tool_calls_log` |
| 章节正文 | `data/projects/{id}/chapters/chapter_NNN.md` | Markdown 文件 |
| 封面图 | `data/projects/{id}/cover.png` | PNG 文件（base64 解码） |
| 用户偏好 | `data/novel.db` | SQLite `user_preferences` |
| Onboarding 状态 | `data/novel.db` | SQLite `onboarding_state` |

**SQLite 选型理由**（`sqlite_store.py:7`）：
- 单机部署，无需额外部署数据库服务
- WAL 模式支持并发读（WS 消息处理期间可并行查询）
- 文件即数据库，备份只需 `cp data/novel.db data/novel.db.bak`

**章节正文存文件理由**（`chapter_repository.py:45`）：
- 单章 1-2 万汉字，BLOB 存 SQLite 不如 Markdown 文件可读
- 可手动编辑/备份/导出
- 文件路径入 `chapters.file_path`，回档时按路径 `unlink`

---

## 2. SQLiteStore

`backend/persistence/sqlite_store.py` 是数据库连接的唯一入口。

### 2.1 设计特点

- **WAL 模式**（`sqlite_store.py:79`）：`PRAGMA journal_mode=WAL`，读写并发
- **外键约束**（`sqlite_store.py:80`）：`PRAGMA foreign_keys=ON`，引用完整性
- **Row Factory**（`sqlite_store.py:77`）：`conn.row_factory = sqlite3.Row`，按列名访问
- **autocommit**（`sqlite_store.py:74`）：`isolation_level=None`，显式控制事务
- **check_same_thread=False**（`sqlite_store.py:75`）：支持跨线程共享连接
- **全局单例**（`sqlite_store.py:100`）：`_store` + `get_store()` 工厂

### 2.2 连接接口

```python
# 自动建表 + 跑迁移
store = SQLiteStore("data/novel.db")

# autocommit 连接
with store.connection() as conn:
    row = conn.execute("SELECT ...").fetchone()

# 显式事务
with store.transaction() as conn:
    conn.execute("INSERT ...")
    conn.execute("UPDATE ...")
    # 异常自动 ROLLBACK
```

### 2.3 全局单例

```python
# sqlite_store.py:97
_store: Optional[SQLiteStore] = None

def get_store(db_path: Path | str = "data/novel.db") -> SQLiteStore:
    """全局单例（首次调用时创建）"""
    global _store
    if _store is None:
        _store = SQLiteStore(db_path)
    return _store
```

测试隔离：`reset_store()`（`sqlite_store.py:108`）重置 `_store = None`。

### 2.4 启动自动迁移

构造时（`sqlite_store.py:21`）自动调用 `_init_schema()`：
1. 创建 `migrations` 表（version PK + applied_at）
2. 读已 applied 的 version 集合
3. 按文件名升序遍历 `migrations/v*.sql`
4. 跳过已 applied 的，对未 applied 的 `executescript()`
5. 写入 `migrations` 表（`INSERT OR IGNORE`）

---

## 3. 数据库 Schema

v003 重构后共 **19 张数据表**（不含 `migrations` 元表）。

### 3.1 表分组总览

| 分组 | 表 | 来源 |
|------|------|------|
| 基础设施 | `conversations`, `messages`, `tool_calls_log`, `user_preferences` | v003 |
| 项目级 | `projects`, `project_state` | v003 |
| 世界树基座 | `world_tree`, `timeline_events`, `geography_locations`, `world_entries` | v003 |
| 角色 | `characters`, `character_relationships` | v003 |
| 结构 | `volumes`, `main_plot`, `sub_plot` | v003 |
| 伏笔 | `seeds` | v003 |
| 章节 | `chapter_status`, `chapters` | v003 |
| Onboarding | `onboarding_state` | v003 |

### 3.2 完整 SQL

迁移文件位于 `backend/persistence/migrations/`：
- `v003_init.sql`：整体重写（按 `spec: .spec/db-refactor/spec.md`）
- `v004_volumes_enhance.sql`：`volumes` 表加 `status` + `summary` 两列

#### 基础设施（4 表）

**conversations**（`v003_init.sql:51`）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | uuid |
| user_id | TEXT NOT NULL | |
| created_at | TIMESTAMP | |
| last_active_at | TIMESTAMP | 每次写消息自动更新 |
| status | TEXT CHECK | `active` / `invalidated` / `archived` |
| invalidated_at | TIMESTAMP | |
| summary | TEXT | |
| message_count | INTEGER DEFAULT 0 | |

索引：`idx_conv_user`, `idx_conv_last_active (DESC)`, `idx_conv_status (user_id, status)`, `idx_conv_invalidated (DESC)`。

**messages**（`v003_init.sql:67`）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | |
| conversation_id | TEXT FK→conversations(id) ON DELETE CASCADE | |
| project_id | TEXT | 软关联（不强制） |
| role | TEXT CHECK | `user` / `assistant` / `system` / `tool` |
| content | TEXT | |
| tool_calls | TEXT (JSON) | |
| tool_results | TEXT (JSON) | |
| agent_name | TEXT | |
| created_at | TIMESTAMP | |

索引：`idx_msg_conv_time`, `idx_msg_role`, `idx_msg_project (project_id, created_at DESC)`, `idx_msg_conv_project`, `idx_msg_agent`。

**tool_calls_log**（`v003_init.sql:88`）：`id, message_id, tool_name, args, result, duration_ms, created_at`。索引：`idx_tclog_msg`, `idx_tclog_tool`, `idx_tclog_time (DESC)`。

**user_preferences**（`v003_init.sql:101`）：复合主键 `(user_id, key)`，外加 `value`, `updated_at`。

#### 项目级（2 表）

**projects**（`v003_init.sql:108`）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | `world-{8hex}` |
| name | TEXT NOT NULL | |
| exploration_level | TEXT DEFAULT 'standard' | `conservative` / `standard` / `wild` |
| cover_image_url | TEXT | `/static/projects/{id}/cover.png` |
| style_pack_id | TEXT | |
| created_at, updated_at | TIMESTAMP | |
| deleted_at | TIMESTAMP | 软删标记 |

索引：`idx_projects_updated (DESC)`, `idx_projects_deleted`。

**project_state**（`v003_init.sql:122`）：1:1 承载运行时高频写字段：`current_pov, current_chapter, current_volume_id, current_timeline_event_id, current_geography_location_ids_json, last_generated_at, updated_at`。PK：`project_id` FK→projects。

#### 世界树基座（4 表）

**world_tree**（`v003_init.sql:131`）：**5 字段最终态** — `project_id (PK)`, `story_core`, `genre_tags_json`, `core_rules_json`, `updated_at`。`core_rules` 是 list[dict]，含 `id / statement / enforcement / applies_to`，`enforcement="hard"` 走 `consistency_checker.check_hard_rules` 扫描。

**timeline_events**（`v003_init.sql:142`）：`id, project_id, era_name, era_order, event_name, description, event_order, start_year, end_year, related_main_plot_node_id, related_char_ids_json, updated_at`。索引：`(project_id, era_order, event_order)`。`start_year` 是 TEXT（支持「男主 15 岁那年」这种语义化时间）。

**geography_locations**（`v003_init.sql:160`）：`id, project_id, name, category, description, significance, parent_location_id, related_char_ids_json, updated_at`。`category` CHECK ∈ `{realm, continent, country, region, city, sect, landmark, other}`。支持嵌套（`parent_location_id` 自引用）。索引：`idx_geography_locations_parent`。

**world_entries**（`v003_init.sql:181`）：通用百科条目 `id, project_id, category, title, content, related_char_ids_json, updated_at`。`category` CHECK ∈ `{magic, tech, social, politics, economy, mythology, history, geography, other}`。索引：`(project_id, category)`。

#### 角色（2 表）

**characters**（`v003_init.sql:201`）：`id, project_id, name, role, traits_json, speech_style, background, updated_at`。`role` CHECK ∈ `{protagonist, deuteragonist, antagonist, supporting, minor}`。索引：`idx_characters_project`, `idx_characters_role`, `idx_characters_name`。

**character_relationships**（`v003_init.sql:218`）：`id, project_id, char_a_id, char_b_id, rel_type, description, updated_at`。`rel_type` CHECK ∈ `{family, lover, friend, ally, rival, enemy, mentor, subordinate}`。**约束**：`UNIQUE(project_id, char_a_id, char_b_id)` + `CHECK(char_a_id < char_b_id)`（由 `project_repository.add_relationship` 规范化保证）。FK：两边都 ON DELETE CASCADE → characters。

#### 结构（3 表）

**volumes**（`v003_init.sql:243`）：`id, project_id, volume_num, title, description, planned_chapter_count, status, summary, updated_at`。**v004 增强**（`v004_volumes_enhance.sql:9`）：加 `status` (in_progress / completed) + `summary` (整卷 1000 字总结)。UNIQUE 索引：`(project_id, volume_num)`。

**main_plot**（`v003_init.sql:255`）：**1:n 节点表**（从旧 PK=project_id 单行结构拆出）。`id, project_id, volume_id, plot_num, title, description, estimated_chapter, status, related_char_ids_json, related_timeline_event_id, related_geography_location_ids_json, updated_at`。`status` CHECK ∈ `{pending, active, completed}`。索引：`(project_id, plot_num)`。

**sub_plot**（`v003_init.sql:274`）：`id, project_id, volume_id, title, description, chapter_start, chapter_end, status, priority, related_char_ids_json, updated_at`。`status` CHECK ∈ `{pending, active, completed, abandoned}`；`priority` CHECK ∈ `{main, side, minor}`。

#### 伏笔（1 表）

**seeds**（`v003_init.sql:295`）：**定义 + 运行时状态合并到单表**。字段：`id (AUTOINCREMENT), project_id, name, content, trigger, payoff, category, scope, estimated_plant_chapter, estimated_payoff_chapter, related_char_ids_json, related_main_plot_node_id, related_sub_plot_id, status, planted_at_chapter, planted_context, last_seen_chapter, weight, updated_at`。`status` CHECK ∈ `{pending, planted, resonating, harvested, abandoned}`。索引：`idx_seeds_project`, `idx_seeds_status (project_id, status)`。

#### 章节（2 表）

**chapter_status**（`v003_init.sql:323`）：复合 PK `(project_id, chapter_num)`。`status` CHECK ∈ `{idle, generating, done, failed}`。`started_at, completed_at, error`。

**chapters**（`v003_init.sql:336`）：复合 PK `(project_id, chapter_num)`。`project_id, chapter_num, volume_id, title, summary, word_count, file_path, intervention, generated_at, updated_at`。**v003 删除**：`actor_feedback / actor_character / detailed_summary` 三个列。索引：`(project_id, chapter_num DESC)`。

#### Onboarding（1 表）

**onboarding_state**（`v003_init.sql:353`）：`project_id (PK), info_state, payload_json, current_step, state_json, last_activity_at, created_at, updated_at`。`info_state` CHECK ∈ `{collecting, wtm_pending, ready}`（v003 新增三态机）。`current_step` + `state_json` 保留兼容旧代码。

### 3.3 v003 删除的旧表

`v003_init.sql:21` 起 DROP 掉 13 张历史表：`projects_deleted`, `style_charter`, `genre_resonance`, `chapter_seed_changes`, `chapter_character_states`, 旧 `main_plot`（PK=project_id），以及 sqlite-vec 历史遗留的 6 张占位表。

---

## 4. Repository 层

`backend/persistence/` 下 9 个 Repository，**全部依赖 `get_store()` 单例**，不持有连接状态。

### 4.1 ProjectRepository

`backend/persistence/project_repository.py`

**职责**：`projects` 表 + 9 张关联表（世界树基座），是最重的 Repository。

#### 关键方法（按表分组）

**projects**：`create / get / list_all / update_name / update_exploration_level / update_style_pack_id / get_style_pack_id / update_cover_image_url / soft_delete / hard_delete / restore_delete`

**project_state**（1:1）：`get_project_state / upsert_project_state`（增量 UPDATE，None 字段不动）

**world_tree**（5 字段最终态）：`_upsert_world_tree (data: dict) / get_world_tree / get_core_rules / save_core_rules`

**volumes**（1:n）：`list_volumes / get_volume / add_volume / update_volume / delete_volume` — v004 起 `update_volume` 允许改 `status` / `summary`

**main_plot**（1:n 节点）：`list_main_plot_nodes / get_main_plot_node / add_main_plot_node / update_main_plot_node / delete_main_plot_node`

**sub_plot**（1:n）：`list_subplots / get_subplot / add_subplot / update_subplot / delete_subplot`

**timeline_events**（1:n）：`list_timeline_events (ORDER BY era_order, event_order) / add / update / delete`

**geography_locations**（1:n，支持嵌套）：`list_geography_locations / add / update / delete`

**world_entries**（1:n）：`list_world_entries (可选按 category 过滤) / add / update / delete`

**characters**（1:n）：`list_characters / get_character / add_character / update_character / delete_character`

**character_relationships**（1:n）：`list_relationships / add_relationship (规范化 char_a_id < char_b_id) / delete_relationship`

**seeds**（1:n，状态合表）：`list_seeds (可选 status 过滤) / get_seed / add_seed (返 lastrowid) / update_seed / delete_seed`

**综合查询**：`load_all_artifacts(project_id) -> Dict[str, Any]`（`project_repository.py:548`）一次性读 11 张表，给 context builder 用。

#### 关键约定

- `_to_json / _from_json` 内部 helper 处理 `*_json` 列
- `add_*` 方法不传 `id` 时按规则自动生成：`vol-{8hex}`, `mp-{8hex}`, `sub-{8hex}`, `evt-{8hex}`, `loc-{8hex}`, `we-{8hex}`, `char-{8hex}`, `rel-{8hex}`
- 增量 UPDATE 模式：`data` dict 缺哪个 key 不动哪一列

#### 关联 Pydantic Model

`Project, ProjectState, WorldTreeRow, VolumeRow, MainPlotNodeRow, SubPlotRow, CharacterRow, CharacterRelationshipRow, SeedRow, TimelineEventRow, GeographyLocationRow, WorldEntryRow`（均位于 `models.py`）

### 4.2 ChapterRepository

`backend/persistence/chapter_repository.py`

**职责**：`chapters` 表 CRUD（**metadata 落 DB + 正文写文件**双写）。

**关键方法**：
- `create()`（`chapter_repository.py:29`）：写 DB 的同时，若 `content_text` 不为 None，落 `file_path` 写 Markdown
- `get / list_by_project (DESC LIMIT N) / get_latest / update_summary / update_intervention / delete / rollback_to (删 > to_chapter) / count_chapters`

**v003 变更**：删 `actor_feedback / actor_character / detailed_summary` 入参；加 `volume_id` 关联。

**关联 Model**：`ChapterRow`

### 4.3 ConversationRepository

`backend/persistence/conversation_repository.py`

**职责**：`conversations` + `messages` 表 CRUD，含 24h 滑窗管理。

**关键方法**（全部 async）：
- `get_active_conversation / get_or_create_active_conversation / get_or_refresh_active_conversation (24h 滑窗)`
- `create_conversation (先 invalidate 旧 active) / invalidate_conversation / get_conversation / list_conversations / update_summary`
- `add_message (自动更新 last_active_at + message_count + 1) / get_messages (DESC LIMIT N) / get_messages_by_project / query_messages (LIKE 关键词搜索)`

**24h 滑窗逻辑**（`conversation_repository.py:48`）：用 `last_active_at` 而非 `created_at`，距最后一次消息 > 24h 时 invalidate 旧 active 并新建。

**关联 Model / Enum**：`Conversation, Message, MessageRole, ConversationStatus`

### 4.4 OnboardingRepository

`backend/persistence/onboarding_repository.py`

**职责**：`onboarding_state` 表 CRUD。**v003 主入口**：`upsert_info_state`（三态机 + payload）。

**关键方法**：
- `get / get_payload / get_info_state / get_state_json (兼容旧)`
- `upsert_info_state (info_state + payload) / set_info_state (仅切状态) / merge_payload (合并到 payload_json)`

**info_state 三态**（`onboarding_repository.py:84`）：`collecting` (管家收信息) → `wtm_pending` (WTM 在跑) → `ready` (基座就绪)。

**关联 Model / Enum**：`OnboardingStateRow, OnboardingInfoState`

### 4.5 ChapterStatusRepository

`backend/persistence/chapter_status_repository.py`

**职责**：`chapter_status` 表 CRUD（章节生成状态机）。

**关键方法**（async + sync 混用）：
- async：`set_status (自动填 started_at/completed_at) / get_status / delete_by_project`
- sync：`delete_after_chapter (rollback 用，project_id + keep_up_to: int)`

**ChapterState**：`idle / generating / done / failed`

### 4.6 ToolCallLogRepository

`backend/persistence/tool_call_log_repository.py`

**职责**：`tool_calls_log` 审计 Repository。

**关键方法**：`add (args/result 序列化为 JSON) / list_by_tool (DESC LIMIT N) / list_by_message (按 message_id)`

### 4.7 UserPreferenceRepository

`backend/persistence/user_preference_repository.py`

**职责**：`user_preferences` 表 CRUD（复合主键 `(user_id, key)`）。

**关键方法**：`set (upsert) / get / list_all`

### 4.8 完整 Pydantic Row Model 清单

`backend/persistence/models.py` 定义了所有 Row Model + 15 个 Enum。

#### Row Model（17 个）

| Model | 表 | 关键字段 |
|-------|----|---------|
| `Conversation` | conversations | id, user_id, status, message_count |
| `Message` | messages | id, conversation_id, role, tool_calls |
| `ToolCallLog` | tool_calls_log | id, tool_name, args, result, duration_ms |
| `UserPreference` | user_preferences | user_id, key, value |
| `ChapterStatus` | chapter_status | project_id, chapter_num, status |
| `Project` | projects | id, name, exploration_level |
| `ProjectState` | project_state | project_id, current_pov, current_chapter |
| `WorldTreeRow` | world_tree | 5 字段（story_core + genre_tags_json + core_rules_json） |
| `TimelineEventRow` | timeline_events | era, event, related_main_plot_node_id |
| `GeographyLocationRow` | geography_locations | name, category, parent_location_id |
| `WorldEntryRow` | world_entries | category, title, content |
| `CharacterRow` | characters | name, role, traits_json |
| `CharacterRelationshipRow` | character_relationships | char_a_id, char_b_id, rel_type |
| `VolumeRow` | volumes | volume_num, title, status, summary |
| `MainPlotNodeRow` | main_plot | plot_num, title, status, related_* |
| `SubPlotRow` | sub_plot | chapter_start/end, status, priority |
| `SeedRow` | seeds | name, content, status, weight |
| `ChapterRow` | chapters | chapter_num, file_path, intervention |
| `OnboardingStateRow` | onboarding_state | info_state, payload_json |

#### Enum（15 个）

`MessageRole, ChapterState, ConversationStatus, CharacterRole, CharacterRelationshipType, SeedStatus, SeedCategory, SeedScope, MainPlotStatus, SubplotStatus, VolumeStatus, SubplotPriority, GeographyCategory, WorldEntryCategory, OnboardingInfoState`

---

## 5. 章节正文文件存储

### 5.1 目录结构

```
data/
├── novel.db                                    # SQLite 主库
└── projects/
    ├── world-3f7a8b2c/
    │   ├── chapters/
    │   │   ├── chapter_001.md
    │   │   ├── chapter_002.md
    │   │   └── chapter_003.md
    │   └── cover.png                           # 封面图
    └── .trash/                                  # 软删暂存
        └── world-3f7a8b2c-20260702103045/      # 软删的完整目录
```

### 5.2 命名规则

`chapter_{NNN}.md` — `chapter_num` 3 位零填充（`chapter_repository.py:234` `f.stem.split("_")[1]`）。

### 5.3 读写接口

**写**（`chapter_repository.py:44`）：`create()` 接收 `content_text` 和 `file_path`，先 `Path(file_path).parent.mkdir(parents=True, exist_ok=True)`，再 `write_text(content_text, encoding="utf-8")`，最后落 DB。

**删**：`delete(project_id, chapter_num)` 只删 DB 行；rollback 时（`chapter_repository.py:234`）同步 `f.unlink()` 删文件。

**回档**（`chapter_repository.py:139`）：`rollback_to(to_chapter)` 删 `chapter_num > to_chapter` 的 DB 行；`ProjectManager.rollback`（`project_manager.py:218`）同步删文件目录里 `chapter_*.md` 中 num > to_chapter 的。

### 5.4 静态文件服务

`backend/api/app.py:76`：

```python
_PROJECTS_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "projects"
app.mount("/static/projects", StaticFiles(directory=str(_PROJECTS_DATA_DIR)), name="project-static")
```

URL 映射：`/static/projects/{project_id}/cover.png` → `data/projects/{project_id}/cover.png`。

---

## 6. 数据迁移机制

### 6.1 自动执行

`SQLiteStore.__init__`（`sqlite_store.py:21`）即触发 `_init_schema()`。无需手动命令。

### 6.2 幂等保证

**应用层**：
- `migrations` 表记录已 applied 的 version
- 已 applied 的 SQL 文件跳过（`sqlite_store.py:42`）
- `INSERT OR IGNORE INTO migrations` 重复执行不报错

**SQL 层**：
- 全部迁移文件 `CREATE TABLE IF NOT EXISTS`
- 索引 `CREATE INDEX IF NOT EXISTS`
- v004 增量 `ALTER TABLE ... ADD COLUMN`（SQLite < 3.35 不支持 IF NOT EXISTS，应用层捕获 `duplicate column` 异常（`sqlite_store.py:48`）静默通过）

### 6.3 新增迁移规范

1. 在 `backend/persistence/migrations/` 新建 `v{NNN}_xxx.sql`
2. 文件名必须 `v` 开头 + `.sql` 结尾（按 `glob("v*.sql")` 排序）
3. 末尾必须包含：
   ```sql
   INSERT OR IGNORE INTO migrations (version, applied_at) VALUES ('v{NNN}_xxx', CURRENT_TIMESTAMP);
   ```
4. 删表操作放文件最前部（按依赖逆序），加表操作放后面
5. 增量 `ALTER TABLE ADD COLUMN` 触发的 `duplicate column` 异常已被 `_init_schema` 静默吃掉，无需手动 try/except
6. v005+ 不在 v003 写过的表上重写 — 增量演进
7. 启动日志会打 `DB {table} {ACTION}: ...` 看 `Repository._log` 字段

---

## 7. 软删除与回档

### 7.1 软删除（ProjectManager.soft_delete / delete）

`backend/services/project_manager.py:244`

```
soft_delete(project_id, confirm=False) → delete(...)
delete(project_id, confirm=False):
  1. if project_path.exists():
       self.trash_root.mkdir(parents=True, exist_ok=True)
       timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
       trash_path = self.trash_root / f"{project_id}-{timestamp}"
       shutil.move(project_path → trash_path)        # 文件目录移入 .trash
  2. self._proj_repo.soft_delete(project_id)         # projects.deleted_at = now
  3. self._proj_repo.hard_delete(project_id)         # DELETE FROM projects (触发 FK CASCADE 清 17 张表)
```

**CASCADE 行为**（v003 全部表 FK 都是 `ON DELETE CASCADE` 到 `projects`）：
- `project_state / world_tree / timeline_events / geography_locations / world_entries / characters / character_relationships / volumes / main_plot / sub_plot / seeds / chapter_status / chapters / onboarding_state` 全部连根删
- `conversations / messages` 走 `idx_msg_project` 软关联，不级联
- **手写清理**：`chapter_status` 走 `delete_by_project`（`chapter_status_repository.py:50`）；`messages.project_id` 不清空（软引用）

**`restore(project_id, trash_name)`**（`project_manager.py:281`）：从 `.trash/{trash_name}/` 移回 `projects/{project_id}/`，并 `restore_delete` 清 `deleted_at`。**注意**：DB 已被 hard_delete 清空，restore 后**只剩文件**，7 件基座/角色/卷/伏笔/章节全丢。所以软删主要是「**文件 + 软标记**」的组合，目的是给用户 7 天后悔期，但 DB 已级联清空。

**安全门**：`confirm=False` 直接 `raise ValueError("delete requires confirm=True")`，必须显式确认。

### 7.2 回档（ProjectManager.rollback）

`backend/services/project_manager.py:211`

```
rollback(project_id, to_chapter, confirm=False):
  1. if not confirm: raise ValueError(...)
  2. kept = count_chapters(project_id)
  3. removed = chapter_repository.rollback_to(to_chapter)  # 删 > to_chapter 的 DB 行
  4. ChapterStatusRepository.delete_after_chapter(keep_up_to=to_chapter)  # 删 > to_chapter 的状态
  5. 遍历 chapters_dir/*.md：if num > to_chapter: f.unlink()  # 删文件
  6. return {kept_chapters, removed_chapters}
```

**回档不删**：`chapters` 保留 ≤ to_chapter；`volumes / main_plot / sub_plot / seeds / world_tree` 等不动；`project_state.current_chapter` 不自动回退（调用方负责同步）。

**安全门**：同 `delete`，`confirm=True` 才执行。

### 7.3 软删项目过滤

`ProjectManager.load`（`project_manager.py:71`）发现 `project.deleted_at is not None` 直接返回 `None`，**前端不会看到软删项目**。
`ProjectRepository.list_all`（`project_repository.py:111`）SQL 自动 `WHERE deleted_at IS NULL`。
