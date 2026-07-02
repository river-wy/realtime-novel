# 后端架构文档

> **最后更新**：2026-07-02
> **版本**：v0.9.6
> **适用 commit**：e717e5b

---

## 目录

1. [整体架构](#1-整体架构)
2. [分层设计](#2-分层设计)
3. [API 层](#3-api-层)
4. [Agent 层](#4-agent-层)
5. [Service 层](#5-service-层)
6. [Persistence 层](#6-persistence-层)
7. [Adapter 层](#7-adapter-层)
8. [Core 层](#8-core-层)
9. [配置系统](#9-配置系统)
10. [启动流程](#10-启动流程)

---

## 1. 整体架构

```
┌────────────────────────────────────────────────────────────────────┐
│                     浏览器（Vue 3 + Vite）                          │
│           HTTP REST + WebSocket（/api/chat）                       │
└─────────────────────────┬──────────────────────────────────────────┘
                          │ baseURL=/api (走 vite 代理 → :7778)
┌─────────────────────────▼──────────────────────────────────────────┐
│                       API 层 (backend/api/)                        │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────┐  ┌────────────┐  │
│  │ ws_manager  │  │ project_     │  │ chapter_ │  │ action_    │  │
│  │ (WS 主对话) │  │ routes       │  │ routes   │  │ routes     │  │
│  ├─────────────┤  ├──────────────┤  └──────────┘  └────────────┘  │
│  │ system_     │  │ CORS + /static/projects 静态服务              │
│  │ routes      │  │                                              │
│  └─────────────┘  │ 入口: backend/api/app.py:create_app()         │
└─────────────────────────┬──────────────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────────────┐
│                      Agent 层 (backend/agent/)                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  NovelSteward（唯一用户入口，backend/agent/agents/novel_     │  │
│  │  steward.py:151） 走 ReAct loop：                            │  │
│  │     ├── ReAct loop ─► 直接调 tool（查项目/Onboarding/图片）  │  │
│  │     ├── delegate_to_agent ──► NovelWriter（章节生成）        │  │
│  │     ├── delegate_to_agent ──► WorldTreeManager（基座干预）   │  │
│  │     └── 落库 ─► Validator（基座/章节一致性校验）             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  runtime: executor.py (AgentExecutor) + session_cache.py           │
│  tools/   : 18+ 工具（project/chapter/character/plot/style/...）  │
└─────────────────────────┬──────────────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────────────┐
│                    Service 层 (backend/services/)                  │
│  ProjectManager │ OnboardingFlow │ InterventionParser             │
│  ConsistencyChecker │ CoverImageGenerator │ OnboardingArtifacts   │
└─────────────────────────┬──────────────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────────────┐
│                  Persistence 层 (backend/persistence/)             │
│  SQLiteStore (连接管理+WAL+自动迁移)                               │
│  ProjectRepository / ChapterRepository / ConversationRepository    │
│  OnboardingRepository / ChapterStatusRepository / ToolCallLog* /  │
│  UserPreferenceRepository                                          │
└─────────────────────────┬──────────────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────────────┐
│                    Adapter 层 (backend/adapters/)                  │
│  LLMAdapter → LLMRouter → DeepSeekProvider / GeminiProvider       │
│  读 agents.json 路由表 + .llm_api_key 取凭证                       │
└────────────────────────────────────────────────────────────────────┘

                ↑↑ Core 层被所有层 import ↑↑
┌────────────────────────────────────────────────────────────────────┐
│                  Core 层 (backend/core/) — 零业务依赖              │
│  WorldTree (内存聚合根) │ core/schemas (7+1 件 Pydantic Schema)     │
│  EventBus (轻量异步事件总线) │ exceptions (RealtimeNovelError 层级) │
└────────────────────────────────────────────────────────────────────┘
```

**请求链示例（用户说"写下一章"）**：

```
浏览器 chat  →  ws_manager.handle_user_message  (api/ws_manager.py:188)
            →  NovelSteward.receive             (agent/agents/novel_steward.py:209)
            →  AgentExecutor.execute (ReAct loop)
            →  delegate_to_agent("novel_writer")
            →  NovelWriter.generate_chapter     (agent/agents/novel_writer.py:75)
            →  executor.execute → tools.generate_chapter 落盘
            →  ConsistencyChecker               (services/consistency_checker.py)
            →  Validator.validate_chapter       (agent/agents/validator.py)
            →  ws_manager 推流式 agent_message → 浏览器
```

---

## 2. 分层设计

### 严格单向依赖

| 层 | 职责 | 允许 import | 禁止 import |
|---|---|---|---|
| `core/` | 领域模型 + 异常 + 事件总线 | 标准库、pydantic | 其他任何层 |
| `adapters/` | 外部服务适配（LLM、图像生成） | core、config | services/agent/api |
| `persistence/` | 数据库 CRUD | core、adapters | services/agent/api |
| `agent/` | LLM 推演引擎 | core、persistence、adapters | services/api |
| `services/` | 业务编排 | core、persistence、agent | api |
| `api/` | HTTP/WS 路由 | 全部 | — |

> 实际生产中部分跨层调用（`api` 调用 `agent` 的 `delegate_chapter_generation`）通过薄路由 + 委托实现，参见 `backend/api/chapter_routes.py:140-149`。

### 设计原则

- **`api/` 是薄路由**：HTTP 序列化/反序列化为主，业务逻辑委托给 `services/` 或 `agent/`。例：`chapter_routes.py:140` 的 `generate_chapter` 直接调 `delegate_chapter_generation()`（`agent/agents/novel_writer.py:227`）。
- **`services/` 编排，不实现**：调 `agent/` 和 `persistence/`，自身不含 LLM 调用或裸 SQL。例：`ProjectManager` 组合 `ProjectRepository` + `ChapterRepository` + `OnboardingRepository`（`backend/services/project_manager.py:18-28`）。
- **`agent/` 纯推演**：不含路由，不含 HTTP 处理，专注 LLM 推演逻辑。Tool 调用通过 `backend/agent/tools/registry.py` 注册表获取。
- **`core/` 零依赖**：被所有层 import 的基础设施。`EventBus` 是单例全局总线（`backend/core/event_bus.py:88`），`exceptions.py:9` 定义 `RealtimeNovelError` 基类层级。

### 异常层级

实现位于 `backend/core/exceptions.py:9-65`：

```
RealtimeNovelError              基类（用户捕获可一把抓）
├── ConfigError                 配置缺失/错误
├── ProjectError                项目相关
│   ├── ProjectNotFoundError
│   ├── ProjectAlreadyExistsError
│   └── ProjectCorruptError
├── LLMError                    LLM 调用相关
│   └── LLMEmptyResponseError
└── GenerationError             章节生成失败
    └── GenerationQualityError
```

---

## 3. API 层

### 入口

实现位于 `backend/api/app.py:42-78`：

- `create_app()` 工厂函数返回 FastAPI 实例（`title="realtime-novel API"`，`version="0.4.0"`）
- `lifespan` 在启动时显式调 `get_store()` 触发 `_init_schema()`，避免"重启后第一次业务请求才建表"
- CORS 全开（`allow_origins=["*"]`，`allow_methods=["*"]`）
- 注册 5 个 router：`system_router`、`project_router`、`chapter_router`、`action_router`、`ws_router`
- 静态文件服务：`/static/projects` → `data/projects/`（封面图等，v0.9 起）

### HTTP 路由表

#### system_routes（`backend/api/system_routes.py`，`/api` 前缀）

| 方法 | 路径 | 行号 | 说明 |
|---|---|---|---|
| GET | `/api/health` | 30 | 健康检查 |
| GET | `/api/info` | 40 | 版本 + LLM provider 列表 |

#### project_routes（`backend/api/project_routes.py`，`/api/projects` 前缀）

| 方法 | 路径 | 行号 | 说明 |
|---|---|---|---|
| GET | `/api/projects` | 89 | 列项目（默认过滤已删除） |
| POST | `/api/projects` | 103 | 创建项目（v0.8 起支持 `exploration_level`） |
| GET | `/api/projects/{id}` | 132 | 加载项目详情（含 7 件基座 + chapters） |
| PATCH | `/api/projects/{id}/exploration-level` | 152 | 切换探索度（conservative/standard/wild） |
| DELETE | `/api/projects/{id}?confirm=true` | 177 | 软删除（v003 实现：仅标 `deleted_at`） |

#### chapter_routes（`backend/api/chapter_routes.py`，`/api/projects` 前缀）

| 方法 | 路径 | 行号 | 说明 |
|---|---|---|---|
| GET | `/api/projects/{id}/chapters` | 57 | 列章节（v0.5 走 DB） |
| GET | `/api/projects/{id}/chapters/{n}` | 75 | 读章节正文（DB 存 file_path，正文从 .md 读） |
| POST | `/api/projects/{id}/chapters` | 123 | 生成下一章（薄路由，委托 `delegate_chapter_generation`） |

#### action_routes（`backend/api/action_routes.py`，`/api/projects` 前缀）

| 方法 | 路径 | 行号 | 说明 |
|---|---|---|---|
| POST | `/api/projects/{id}/interventions` | 37 | 提交剧情干预（实际走 WTM ReAct） |
| POST | `/api/projects/{id}/rollback?to_chapter&confirm` | 80 | 回档（薄路由，调 `update_base` 改基座） |
| POST | `/api/projects/{id}/image` | 129 | 生成主立绘（薄路由，调 `generate_image` tool） |
| PATCH | `/api/projects/{id}/base` | 179 | 改 7 件基座（薄路由，调 `update_base` tool） |

### WebSocket：`/api/chat`（`backend/api/ws_manager.py:82`）

**唯一对话端点（v0.6 改造后）** — 所有用户消息统一进 `/api/chat`，由 `NovelSteward` 处理（不再分流到不同入口）。

#### 接收消息类型

| type | 说明 | 处理位置 |
|---|---|---|
| `user_message` | 用户消息 | 启动 `handle_user_message` Task 调管家 |
| `interrupt` | 中断当前生成 | `ws_manager.interrupt(user_id)` |
| `confirm` | 二次确认 | 先 echo（v0.6 s3 阶段占位） |
| `ping` | 心跳 | 回 `pong` |

#### 推送事件类型（spec.md §4.4）

| type | 含义 | 触发时机 |
|---|---|---|
| `agent_thinking` | LLM 思考中 | 管家/下游 Agent 每次 LLM 调用前 |
| `tool_calling` | Agent 准备调 tool | 调工具前 |
| `tool_result` | tool 执行结果 | 调工具后 |
| `agent_message` | 管家最终回复 | 整轮推演完成（含 `structured_data` 供前端渲染） |
| `confirm_required` | 危险操作需二次确认 | WTM 判定 `requires_double_confirm=true` |
| `interrupted` | 用户主动中断 | 用户发 `interrupt` 或 Task 被取消 |
| `error` | 失败 | 异常 / 任务忙 (`TASK_BUSY`) / 非法消息类型 (`INVALID_MESSAGE_TYPE`) |

#### 消息流（`handle_user_message` 完整流程，ws_manager.py:188-280）

```
WS 收到 user_message
  → 检查 ws_manager.has_active_task → 忙则返 error: TASK_BUSY
  → conv_repo.get_or_refresh_active_conversation (24h 滑窗)
  → conv_repo.add_message (落 user 消息)
  → 推 agent_thinking
  → NovelSteward.receive() — 走 ReAct loop
  → _push_agent_trace(result) — 推 tool_calling + tool_result + agent_thinking
  → 若 result.structured_data.require_confirm → 推 confirm_required
  → 推 agent_message（最终回复）
  → conv_repo.add_message (落 assistant 消息，tool_calls 字段存 intent/downstream)
```

#### WS 连接管理

- 单例 `WebSocketManager`（`ws_manager.py:30`）— 进程内全局
- 字典 `connections: dict[user_id, WebSocket]` — 单机单用户（`user_id = "anonymous"`）
- 字典 `active_tasks: dict[user_id, asyncio.Task]` — 同一 user 串行执行
- 异常断开 → `WebSocketDisconnect` 触发 `disconnect` 清理 task 引用

### CORS 与静态文件

- CORS：完全开放（`app.py:62-69`），方便本地 dev 跨端口调试
- 静态服务：`/static/projects` → `data/projects/`（`app.py:75-77`），用于封面图 URL 公开访问

---

## 4. Agent 层

### 顶层 Agent 矩阵

| Agent | 文件 | 行号 | 职责 |
|---|---|---|---|
| **NovelSteward** | `backend/agent/agents/novel_steward.py:151` | 唯一用户入口；ReAct loop 自主决策；超范围委托专家 |
| **NovelWriter** | `backend/agent/agents/novel_writer.py:45` | 章节正文生成 + 落盘 + 1 句话 summary |
| **WorldTreeManager** | `backend/agent/agents/world_tree_manager.py:149` | 基座干预分析 / Onboarding 完整基座规划 / 卷总结 / 卷完结 |
| **Validator** | `backend/agent/agents/validator.py:86` | 校验 Agent（基座一致性 + 章节内容合理性） |

> Validator 不在 spec 顶层三 Agent 之内，但被 WTM 和 Writer 落库后联动调用，是 v0.9 重构引入的"审判"层（`validator.py:5-23`）。

### 管家工作流（NovelSteward）

实现位于 `backend/agent/agents/novel_steward.py:209-294`：

```
用户消息
  ↓
构造 session_key = f"{user_id}:{conv_id}:novel_steward"  (3 维唯一)
  ↓
SessionCacheManager.has_valid_cache → 命中/未命中
  ├─ 未命中 → load_chat_history (DB 拉 15 轮) → rebuild cache
  └─ 命中 → 跳过 DB 查询
  ↓
AgentExecutor.execute(
  agent_name="novel_steward",
  system_prompt=STEWARD_SYSTEM_PROMPT,  (291 行身份+职责+Onboarding 流程)
  user_message=...,
  history=...,
  session_key=session_key,
  max_iterations=15,
)
  ↓
executor_output = {final_response, structured_data, tool_calls_history, iterations, duration_ms, error}
  ↓
包装返回 {intent="chat", response=..., structured_data=..., downstream_called=..., ...}
```

管家在 ReAct loop 内可调：

- **职责范围内**（直接调 tool）：`create_project` / `load_project` / `delete_project` / `generate_image` / `update_exploration_level` / `verify_world_tree_baseline` / `adjust_style` / `list_style_packs`
- **职责范围外**（委托专家）：
  - `delegate_to_agent("novel_writer")` — 同步等待章节生成
  - `delegate_to_agent("world_tree_manager", intent="intervention")` — 同步等待基座干预
  - `dispatch_background_task(task_type="generate_cover")` — 异步，后台生成封面
- **禁止**（v0.8 改造）：`edit_artifact` / `update_base` 已从管家白名单移除，改基座必须委托 WTM

### 文笔家工作流（NovelWriter）

实现位于 `backend/agent/agents/novel_writer.py:75-189`：

```
delegate_chapter_generation(project_id, intervention=None, source=...)  # agent/agents/novel_writer.py:227
  ↓
_validate_world_tree_completeness(project_id)  # 5 项完整性校验 (writer.py:200-225)
  ├─ 失败 → ChapterOutput(error=...) 直接熔断
  └─ 通过 →
       NovelWriter.generate_chapter 走 executor.execute (writer.py:75)
       调 generate_chapter / summarize_chapter tool 落盘
  ↓
ConsistencyChecker.check_hard_rules + check_world_entries  (services/consistency_checker.py)
  ↓
Validator.validate_chapter (validator.py)
  ├─ PASS/WARN → 直接落
  ├─ BLOCKED → retry 一次 (用 issues 注入 user_message)
  │   ├─ retry PASS/WARN → 落
  │   └─ retry BLOCKED → 在正文加 [unverified] 标记后落
  └─ FATAL → 视情况
```

> 章节生成耗时端到端 60-100s（`chapter_routes.py:122` 注释），前端 axios timeout 120s（`frontend/src/api/client.ts:11`）。

### 世界树管理工作流（WorldTreeManager）

实现位于 `backend/agent/agents/world_tree_manager.py`：

- **干预分析** `analyze_intervention(project_id, text)` (line 538) — 调 ReAct loop 自主决定改哪些基座 + 埋伏笔，落库后调 Validator
- **基座调整** `analyze_base_adjustment(project_id, text)` (line 647) — 与干预类似但 `intent="adjust_base"`
- **Onboarding 完整基座** `run_initial_baseline_react(project_id, steward_payload)` (line 735) — 管家收集 6 维信息后委托 WTM 自主落 9 张表
- **卷总结** `generate_volume_summary(project_id, volume_id)` (line 332) — ~1000 字总结，存到 `volumes.summary`
- **卷完结** `complete_volume(project_id, volume_id, auto_generate_summary=True)` (line 422) — 自动生成 summary 后改 `volumes.status="completed"`
- **联动回滚**（v0.9 新增）：Validator 返 FATAL → `_rollback_all_writes`；BLOCKED → `_rollback_issue_rows` 精准回滚

### Session Cache（`backend/agent/runtime/session_cache.py`）

- **目的**：避免每次 ReAct 重新从 DB 拉历史 messages
- **维度**：`user_id + conversation_id + agent_name` 三维 key
- **生命周期**：进程内 LRU；重启后从 DB rebuild
- **轮次**：管家 `session_rounds=15`（`novel_steward.py:262`）

### Tool Registry（`backend/agent/tools/registry.py`）

- 18+ 工具分类注册：`project_tools.py` / `chapter_tools.py` / `character_tools.py` / `plot_tools.py` / `style_tools.py` / `volume_tools.py` / `delegation_tools.py` / `onboarding_tools.py` / `image_tools.py` / `edit_artifact_tool.py` / `summarize_chapter_tool.py` / `exploration_tools.py` / `base_edit_tools.py` / `pov_tools.py`
- Tool 入口 `get_tool(name)` 返回 Tool 实例，LLM 在 ReAct loop 中按 OpenAI function calling 协议调

---

## 5. Service 层

服务层负责业务编排，不含 LLM 调用或裸 SQL。

| Service | 文件 | 行数 | 职责 |
|---|---|---|---|
| `ProjectManager` | `backend/services/project_manager.py:21` | 291 | 项目 CRUD / 软删除 / 回档 / trash 恢复 |
| `OnboardingFlow` | `backend/services/onboarding_flow.py:30` | 111 | Onboarding 状态机（**DEPRECATED** v003，保留 HTTP 路由兜底） |
| `OnboardingArtifacts` | `backend/services/onboarding_artifacts.py` | — | Onboarding 状态查询 + payload 合并（管家 ReAct 流程配套） |
| `InterventionParser` | `backend/services/intervention_parser.py:13` | — | 剧情干预解析（HTTP 路由调用，实质仍走 WTM） |
| `ConsistencyChecker` | `backend/services/consistency_checker.py:10` | — | 硬约束扫描 + 知识库矛盾检测（Writer 落盘后调） |
| `CoverImageGenerator` | `backend/services/cover_image_generator.py` | — | 封面 prompt 构造 + Gemini 生图 + 落盘 |

---

## 6. Persistence 层

### SQLiteStore

实现位于 `backend/persistence/sqlite_store.py:13-95`：

- **WAL 模式**：`PRAGMA journal_mode=WAL`（`sqlite_store.py:55`），读写并发不互锁
- **外键**：`PRAGMA foreign_keys=ON`（`sqlite_store.py:56`）
- **自动迁移**：启动时按文件名顺序跑 `migrations/v*.sql`，已执行的写入 `migrations` 表跳过（`sqlite_store.py:23-43`）
- **事务**：`transaction()` contextmanager 显式 `BEGIN/COMMIT/ROLLBACK`（`sqlite_store.py:71-79`）
- **单例**：`get_store()` 进程内全局，工厂模式首次调时建库

#### 迁移文件

```
backend/persistence/migrations/
├── v003_init.sql         # 整体重写：20 张表（spec: .spec/db-refactor/spec.md）
└── v004_volumes_enhance.sql  # volumes 加 status + summary 字段
```

### Repository 列表

`backend/persistence/__init__.py` 导出：

| Repository | 文件 | 职责 |
|---|---|---|
| `ProjectRepository` | `project_repository.py` | 项目 + 7 件基座（19 张表） + characters / volumes / seeds / world_entries / timeline_events / geography_locations CRUD |
| `ChapterRepository` | `chapter_repository.py` | 章节元数据（file_path / summary / word_count），正文存文件 |
| `ChapterStatusRepository` | `chapter_status_repository.py` | 章节状态流（in_progress / done） |
| `OnboardingRepository` | `onboarding_repository.py` | `onboarding_state` 表（current_step + payload） |
| `ConversationRepository` | `conversation_repository.py` | 24h 滑窗 active conversation + messages 流 |
| `ToolCallLogRepository` | `tool_call_log_repository.py` | 工具调用审计日志（完整链路追踪） |
| `UserPreferenceRepository` | `user_preference_repository.py` | 用户偏好（默认探索度等） |

### 章节正文存储

- 路径：`data/projects/{project_id}/chapters/chapter_NNN.md`
- DB `chapters.file_path` 存相对路径（`PROJECT_ROOT` 锚定）
- `chapter_routes.py:75-99` 读章节时优先用 DB title，若 DB title 是"第N章"占位符则从正文首行 `# ` 提取

---

## 7. Adapter 层

### LLM 调用流

```
LLMRequest (adapters/types.py:30)
  → LLMAdapter.complete() (adapters/llm_adapter.py)
  → LLMRouter.get_provider_by_name(model_name) (adapters/llm_router.py:40)
  → DeepSeekProvider / GeminiProvider
  → LLMResponse
```

### ModelRole（`backend/adapters/types.py:18-21`）

| Role | model_name | Provider |
|---|---|---|
| `TEXT` | `friday/deepseek-v4-pro-tencent` | `DEEPSEEK` |
| `IMAGE` | `friday/gemini-3.1-flash-image-preview` | `GEMINI` |

### LLMRouter

实现位于 `backend/adapters/llm_router.py:18-69`：

- 路由表来源：`agents.json` 的 `models` 字典（`llm_router.py:18-22`）
- 静态映射 `_MODEL_TO_PROVIDER` 作 fallback（`llm_router.py:21-24`）
- `get_router()` 单例，首次调时按 `agents.json` 构造 provider 字典
- `get_provider(role)` 保留旧接口（向后兼容）

### Provider 实现

- **DeepSeekProvider**：`backend/adapters/providers/deepseek.py`
  - 协议：`openai_compat`（OpenAI Chat Completions 兼容）
  - 端点：`https://aigc.sankuai.com/v1/openai/native`（`agents.json:13`）
  - 模型：`deepseek-v4-pro-tencent`（`context_window=128000`，`supports_thinking=true`）
- **GeminiProvider**：`backend/adapters/providers/gemini.py`
  - 协议：`google_native`（submit + 轮询）
  - submit：`https://aigc.sankuai.com/v1/google/models/gemini-3.1-flash-image-preview:imageGenerate`
  - query：`{operation_id}:imageGenerateQuery` 模板
  - `poll_interval=3s`，`poll_timeout=120s`

### LLMRequest / LLMResponse

实现位于 `backend/adapters/types.py:30-78`：

- LLMRequest 支持 `messages[]`（多轮）+ `tools[]`（OpenAI function calling）+ `enable_thinking`
- LLMResponse 含 `tool_calls: List[ToolCall]` — 走 ReAct 协议
- LLMStreamChunk 支持 `tool_calls_delta` 流式累积

---

## 8. Core 层

### WorldTree 聚合根

实现位于 `backend/core/world_tree.py:25-43`：

```python
@dataclass
class WorldTree:
    world_tree: WorldTreeSchema
    genre_resonance: GenreResonanceSchema
    main_plot: MainPlotSchema
    character_card: CharacterCardSchema
    sub_plot: SubPlotSchema
    seed_table: SeedTableSchema
    style_pack_id: Optional[str] = None
```

- **角色**：内存中聚合 7 件 Schema（v0.4.1 入库后此聚合根主要用于序列化/统计）
- **序列化**：`to_dict() / from_dict()`（`world_tree.py:45-72`）
- **统计**：`summary()` 返回每件的关键计数（`world_tree.py:79-86`）
- **注**：v0.8.2 删 `from_project_dir / to_project_dir`；v0.9 删 `add_node / rollback_to`（branches_json 列已删）

### 7 件基座 + 1 件章节摘要 Schema

实现位于 `backend/core/schemas/`：

| Schema | 文件 | 内容 |
|---|---|---|
| `WorldTreeSchema` | `world_tree.py` | 时间线 + 地理 + 核心规则 + 主线/支线节点树 |
| `GenreResonanceSchema` | `genre_resonance.py` | 题材 + 情绪基调 |
| `MainPlotSchema` | `main_plot.py` | 主线弧线 + beats |
| `SubPlotSchema` | `sub_plot.py` | 支线 thread 列表 |
| `CharacterCardSchema` | `character_card.py` | 角色 + 关系 |
| `SeedTableSchema` | `seed_table.py` | 伏笔/种子 |
| `StyleCharterSchema` | `style_charter.py` | 笔风 schema（v0.8 引入） |
| `ChapterSummarySchema` | `chapter.py` | 章节级摘要（planted/resonating/harvested 种子变化） |

### EventBus

实现位于 `backend/core/event_bus.py:23-89`：

- **零第三方依赖**，纯 asyncio
- **装饰器注册**：`@event_bus.on("onboarding.step4_confirmed")`（`event_bus.py:41`）
- **fire-and-forget**：`emit` 立即返回，handler 后台并发跑（`event_bus.py:65-85`）
- **task 引用保存**：防 GC 提前回收（`event_bus.py:78-81`）
- **异常隔离**：handler 异常不影响调用方（`event_bus.py:75-84`）
- **单例**：`event_bus = EventBus()`（`event_bus.py:89`）

#### 已知事件

| 事件 | 触发位置 | 监听者 |
|---|---|---|
| `onboarding.step4_confirmed` | WTM 完成初始基座后 | `backend/agent/onboarding/hooks.py`（项目名同步 + 封面生成） |

### exceptions

实现位于 `backend/core/exceptions.py:9-65`，详见 [§2 异常层级](#2-分层设计)。

---

## 9. 配置系统

### agents.json（`backend/config/agents.json`）

实现位于 `backend/config/agents.json`，73 行，三段式：

#### 1. `exploration_levels`（line 3-32）

项目级 LLM 参数档位，按 `projects.exploration_level` 查表注入：

| Level | temperature | max_tokens | frequency_penalty | chapter_word_count | 语义 |
|---|---|---|---|---|---|
| `conservative` | 0.6 | 8192 | 0.1 | 5000 | 严守用户输入，AI 补充少 |
| `standard` | 0.85 | 8192 | 0.3 | 5000 | 平衡，日常创作 |
| `wild` | 1.05 | 8192 | 0.5 | 5000 | 大胆发散 |

> chapter_word_count 是精确值，注入 prompt 时转 `[N×0.95 ~ N×1.05]` 浮动范围。

#### 2. `models`（line 33-54）

可用模型池，每个 model 含：

- `protocol`（`openai_compat` / `google_native`）
- `base_url` 或 `submit_url` / `query_url_template`
- `default_params`
- `context_window` / `supports_thinking`

#### 3. `agents`（line 55-73）

`agent_name → model_name` 路由表：

```json
{
  "novel_steward":      "friday/deepseek-v4-pro-tencent",
  "novel_writer":       "friday/deepseek-v4-pro-tencent",
  "world_tree_manager": "friday/deepseek-v4-pro-tencent",
  "memory_keeper":      "friday/deepseek-v4-pro-tencent",
  "image_generator":    "friday/gemini-3.1-flash-image-preview"
}
```

> Agent `model` 字段必须与代码侧 `AgentConfig.agent_name` 保持一致，供 `_get_context_window` 等函数直接索引。

### .llm_api_key（gitignored）

实现位于 `backend/config/config_loader.py:22-25`（路径定义）+ 加载逻辑 `load_llm_api_key()`：

- **路径**：`PROJECT_ROOT / ".llm_api_key"`
- **格式**：标准 JSON
  ```json
  { "FRIDAY_API_KEY": "21899390080843030554" }
  ```
- **加载失败**抛 `ConfigError`（`config_loader.py:33`）
- **缓存**：进程内 `_llm_api_key_cache`（`config_loader.py:30`）

### LLM 路由流程

```
LLMRequest (含 role=TEXT / IMAGE)
  → LLMRouter.get_provider(role)  [llm_router.py:54]
  → ModelRole → ModelProvider 映射
  → DEEPSEEK → DeepSeekProvider
  → GEMINI   → GeminiProvider
  → POST base_url + api_key (从 .llm_api_key 读)
  → LLMResponse
```

---

## 10. 启动流程

### 一键启动脚本

实现位于 `scripts/start.sh`（149 行）。

#### 端口约定（start.sh:7-10）

| 服务 | 端口 | 配置位置 |
|---|---|---|
| 前端 dev server | `http://localhost:7777` | `frontend/vite.config.ts` |
| 后端 API | `http://127.0.0.1:7778` | `pyproject.toml` + `start.sh:11` |
| API 代理 | `/api` → 后端 7778 | `frontend/vite.config.ts` |

> 调整端口改 start.sh 3 个常量 + 同步改 vite.config.ts + pyproject.toml，不要散落改。

#### 启动步骤

1. **前置检查**（`start.sh:79-127`）
   - `check_llm_api_key`：校验 `.llm_api_key` 存在 + 非空 + JSON 格式
   - `check_dependencies`：校验 `.venv` + `frontend/node_modules` 存在
2. **端口清理**（`start.sh:60-103`）
   - `lsof` 查占用 → cmdline 匹配 `realtime.novel | uvicorn.*backend.api | vite --port` → `kill` 清理本项目进程
   - 非本项目进程占用 → 报错退出
3. **启动后端**（`start.sh:106-129`）
   - `nohup uvicorn backend.api.app:app --host 127.0.0.1 --port 7778 --log-level info` → `tmp/logs/backend.log`
   - 轮询 `/api/health` 最长 15s 就绪
4. **启动前端**（`start.sh:132-150`）
   - `nohup npm run dev -- --port 7777` → `tmp/logs/frontend.log`
   - 轮询 `http://localhost:7777/` 最长 15s 就绪
5. **后端就绪后**：
   - `app.py:34-39` 的 `lifespan` 调 `get_store()` 触发 `_init_schema()` 自动建表
   - `app.py:42-50` 的 `create_app()` 注册 CORS / 5 个 router / 静态文件服务

#### 启动后端时实际发生的初始化

```
uvicorn 加载 backend.api.app
  → configure_logging()         [app.py:18-21]
  → import backend.api.* 触发各 router 模块加载
  → import backend.agent.onboarding.hooks  [app.py:33]
     → 触发 EventBus.on("onboarding.step4_confirmed") 注册
  → app.include_router(*)
  → app.mount("/static/projects", StaticFiles(...))
  → lifespan startup:
       get_store()
         → SQLiteStore.__init__()
           → _init_schema() 跑 migrations/v003 + v004
  → uvicorn accept connections on :7778
```

#### 停止

- `scripts/stop.sh` — 按 `tmp/pids/*.pid` 杀进程

#### 日志

- `tmp/logs/backend.log` — uvicorn + 应用日志
- `tmp/logs/frontend.log` — Vite dev server 日志

---

## 附录：文件位置速查

```
backend/
├── __init__.py            # 包入口，导出 7+1 Schema + WorldTree + __version__
├── __main__.py            # CLI 入口（python -m backend）
├── api/                   # 5 个 router + app.py 工厂
├── agent/
│   ├── agents/            # 4 个顶层 Agent（Steward / Writer / WTM / Validator）
│   ├── runtime/           # AgentExecutor + SessionCache
│   ├── tools/             # 18+ 工具
│   ├── prompts/           # 提示词组装
│   └── onboarding/        # Onboarding hooks
├── services/              # 6 个 service（编排层）
├── persistence/           # SQLiteStore + 7 个 Repository
│   ├── migrations/        # v003_init.sql + v004_volumes_enhance.sql
│   └── models.py          # ORM 数据类
├── adapters/              # LLM Adapter + Router + Providers
│   └── providers/         # deepseek.py + gemini.py
├── core/                  # 零业务依赖
│   ├── world_tree.py      # 内存聚合根
│   ├── event_bus.py       # 异步事件总线
│   ├── exceptions.py      # 异常层级
│   └── schemas/           # 7+1 Pydantic Schema
├── config/
│   ├── agents.json        # 模型池 + 探索度 + agent 路由
│   └── config_loader.py   # .llm_api_key + agents.json 加载
└── utils/                 # logger / version

scripts/
├── start.sh               # 一键启动
└── stop.sh                # 一键停止

data/                      # 运行时数据（gitignored）
├── novel.db               # SQLite
└── projects/              # 章节 .md + 封面图
    └── {project_id}/
        ├── chapters/chapter_NNN.md
        └── cover.png

.llm_api_key               # gitignored，FRIDAY_API_KEY
```
