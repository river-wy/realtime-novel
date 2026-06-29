# 后端技术架构文档

> **最后更新**：2026-06-29
> **版本**：v0.9.x

---

## 目录

1. [整体架构概览](#1-整体架构概览)
2. [分层设计与依赖规则](#2-分层设计与依赖规则)
3. [API 层（api/）](#3-api-层)
4. [Agent 层（agent/）](#4-agent-层)
5. [Service 层（services/）](#5-service-层)
6. [Adapter 层（adapters/）](#6-adapter-层)
7. [领域核心层（core/）](#7-领域核心层)
8. [配置系统（config/）](#8-配置系统)
9. [日志系统](#9-日志系统)

---

## 1. 整体架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                      浏览器（Vue 3）                            │
│            HTTP REST + WebSocket（/api/chat）                   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                   API 层（FastAPI）                              │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐   │
│  │ ws_manager   │  │ project/     │  │ chapter/action/      │   │
│  │ /api/chat WS │  │ system_routes│  │ system_routes HTTP   │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬──────────┘   │
└─────────┼─────────────────┼──────────────────────┼─────────────┘
          │                 │                      │
┌─────────▼─────────────────▼──────────────────────▼─────────────┐
│                   Agent 层（LLM 推演）                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  NovelSteward（管家，唯一用户入口）                      │    │
│  │  AgentExecutor ReAct loop → tool → LLM → tool → ...    │    │
│  │       ├── delegate_to_agent ──► NovelWriter             │    │
│  │       └── delegate_to_agent ──► WorldTreeManager        │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                   Service 层（业务编排）                        │
│  OnboardingFlow │ ProjectManager │ ConsistencyChecker │ ...     │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                   Persistence 层（SQLite）                      │
│  SQLiteStore │ ProjectRepository │ ChapterRepository │ ...      │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                   Adapter 层（外部服务）                        │
│  LLMAdapter → LLMRouter → DeepSeekProvider / GeminiProvider    │
└─────────────────────────────────────────────────────────────────┘

     ↑↑ 所有层都可 import ↑↑
┌─────────────────────────────────────────────────────────────────┐
│                   Core 层（领域模型，零依赖）                   │
│  WorldTree / Schemas / Exceptions / EventBus                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 分层设计与依赖规则

### 严格单向依赖

| 层 | 职责 | 允许 import | 禁止 import |
|---|---|---|---|
| `core/` | 领域 Schema + 异常 + 事件总线 | 标准库、pydantic | 其他任何层 |
| `adapters/` | 外部服务适配（LLM） | core | services/agent/api |
| `persistence/` | 数据库 CRUD | core、adapters | services/agent/api |
| `agent/` | LLM 推演引擎 | core、persistence、adapters | services/api |
| `services/` | 业务编排 | core、persistence、agent | api |
| `api/` | HTTP/WS 路由 | 全部 | — |

违反此规则会导致循环依赖，PR Review 会 -1。

### 设计原则

- **`api/` 是薄路由**：只做 HTTP 序列化/反序列化，业务逻辑委托给 `services/`
- **`services/` 编排，不实现**：调 `agent/` 和 `persistence/`，自身不含 LLM 调用或 SQL
- **`agent/` 纯推演**：不含路由，不含 HTTP 处理，专注 LLM 推演逻辑
- **`core/` 零依赖**：任何层都可安全 import，是跨层共享的基础设施

---

## 3. API 层

### FastAPI 应用入口（`api/app.py`）

```
app = FastAPI(title="realtime-novel API", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# 注册路由
app.include_router(system_router)    # GET /api/health, /api/info
app.include_router(project_router)   # 项目 CRUD
app.include_router(chapter_router)   # 章节读取/生成
app.include_router(action_router)    # 干预/回档/图片/基座
app.include_router(ws_router)        # WS /api/chat

# 静态文件服务（封面图）
app.mount("/static/projects", StaticFiles(directory="data/projects"))
```

### WebSocket 主对话端点（`api/ws_manager.py`）

WebSocket 是前后端实时通信的核心通道，所有用户消息统一由此进入。

**连接管理**：

```
class WebSocketManager:
    connections: dict[str, WebSocket]  # user_id → WS 连接
    active_tasks: dict[str, asyncio.Task]  # user_id → 正在跑的任务
```

**消息处理流程**：

```
客户端 → send_json({type: "user_message", content, project_id})
         ↓
WS 端点接收 → 检查是否有 active_task
         ↓
asyncio.create_task(handle_user_message(...))
         ↓
handle_user_message():
  1. 管理 conversation（24h 滑窗）
  2. 落 user message 到 DB
  3. push {type: "agent_thinking"}
  4. await NovelSteward.receive(...)
  5. push tool_calling + tool_result（ReAct trace）
  6. push {type: "agent_message", content, structured_data}
  7. 落 assistant message 到 DB
```

**支持的事件类型**：

| 方向 | 类型 | 说明 |
|------|------|------|
| 客→服 | `user_message` | 用户消息 |
| 客→服 | `interrupt` | 取消当前生成 |
| 客→服 | `ping` | 心跳 |
| 服→客 | `agent_thinking` | LLM 思考中 |
| 服→客 | `tool_calling` | 工具调用中 |
| 服→客 | `tool_result` | 工具执行结果 |
| 服→客 | `agent_message` | 最终回复（含 `structured_data`） |
| 服→客 | `confirm_required` | 危险操作需二次确认 |
| 服→客 | `error` | 错误 |
| 服→客 | `interrupted` | 已中断 |
| 服→客 | `pong` | 心跳响应 |

### HTTP 路由

| 文件 | 路由前缀 | 主要端点 |
|------|---------|---------|
| `project_routes.py` | `/api/projects` | 项目 CRUD + 探索度切换 |
| `chapter_routes.py` | `/api/projects/{id}/chapters` | 章节列表 / 读取 / 生成 |
| `action_routes.py` | `/api/projects/{id}/...` | 干预 / 回档 / 图片 / 基座修改 |
| `system_routes.py` | `/api` | health + info |

---

## 4. Agent 层

Agent 层是系统的核心，实现了基于 ReAct（Reasoning + Acting）模式的 LLM 推演引擎。

### 4.1 三顶层 Agent

#### NovelSteward（小说管家）

**文件**：`agent/agents/novel_steward.py`

用户唯一入口。所有消息（首页聊天 / 项目内聊天 / 创建项目 / 闲聊）都先由管家接收。

```
职责范围内（直接用工具）：
  - 项目管理：create/load/delete_project
  - Onboarding：onboarding_propose_step / onboarding_user_confirm / onboarding_generate_chapter
  - 基座轻量编辑：edit_artifact
  - 图片生成：generate_image
  - 探索度：update_exploration_level

职责范围外（委托专家）：
  - 生成章节正文 → delegate_to_agent(agent="novel_writer")
  - 复杂基座联动干预 → delegate_to_agent(agent="world_tree_manager")
  - 后台任务（封面生成等）→ dispatch_background_task(task_type="generate_cover")
```

**委托原则**：「用户在等这个结果吗？」
- 是 → `delegate_to_agent`（同步，等待专家完成后再回复用户）
- 否 → `dispatch_background_task`（异步，立即回复用户，后台执行）

#### NovelWriter（文笔家）

**文件**：`agent/agents/novel_writer.py`

负责章节正文生成 + summary 抽取 + 文风控制 + 历史承接。

- 不决定剧情走向（走向由世界树基座约束）
- 不修改任何基座（只读）
- 通过 MemoryKeeper 检索历史章节上下文

#### WorldTreeManager（世界树管理）

**文件**：`agent/agents/world_tree_manager.py`

负责基座一致性 + 干预影响分析 + 种子预留 + 走向调整 + diff 输出。

- 不生成章节正文（写不是它的职责）
- 不直接和用户对话（通过管家中转）
- 调用 MemoryKeeper 检索历史干预

### 4.2 ReAct 执行引擎（`agent/runtime/executor.py`）

`AgentExecutor` 是所有 Agent 共享的 ReAct loop 执行引擎。

```
class AgentExecutor:
    async def execute(
        agent: AgentConfig,      # agent_name + system_prompt + extra_tools
        user_message: str,
        project_id: Optional[str],
        history: Optional[List[dict]],
        session_key: Optional[str],  # 启用 session cache
        max_iterations: int = 7,
    ) -> AgentOutput
```

**ReAct Loop 工作流**：

```
┌─────────────────────────────────────────────────────────┐
│  初始化 messages（system + history + context + user）   │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│  iteration 1..max_iterations:                           │
│    await llm.complete(messages, tools)                  │
│         ↓                                               │
│    有 tool_calls?                                       │
│         ├── YES → 执行 tool → append 结果到 messages → │
│         │         继续下一个 iteration                  │
│         └── NO  → final_response → break               │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│  写回 session cache（delta 追加）                        │
│  触发 Middleware 后置节点                               │
│  返回 AgentOutput                                       │
└─────────────────────────────────────────────────────────┘
```

**AgentOutput 标准结构**：

```
class AgentOutput(BaseModel):
    final_response: str           # LLM 最终自然语言回复
    structured_data: dict         # 工具产生的结构化数据
    tool_calls_history: List[dict]  # 完整调用链路
    iterations: int               # 实际执行轮次
    input_tokens: int
    output_tokens: int
    duration_ms: int
    error: Optional[str]
    needs_review: bool            # 后置节点标记需人工审核
    skip_response: bool           # 后置节点拦截回复
```

**Middleware 后置节点插槽**：

```
executor = get_agent_executor()

@executor.middleware()                          # 全局（所有 Agent）
async def safety_check(output: AgentOutput, ctx: dict) -> AgentOutput:
    ...
    return output

@executor.middleware(agent_name="novel_writer") # 仅对文笔家生效
async def quality_check(output: AgentOutput, ctx: dict) -> AgentOutput:
    ...
    return output
```

### 4.3 Session Cache（`agent/runtime/session_cache.py`）

进程内 session cache，避免每次请求都重建对话历史。

- **cache key**：`{user_id}:{conv_id}:{agent_name}`
- **cache hit**：直接复用 messages，只追加新 user_message
- **cache miss**：从 DB 加载历史（15 会话轮），rebuild
- **超长压缩**：cache 超过阈值时异步触发 LLM summary 压缩，不阻塞返回

### 4.4 工具系统（`agent/tools/`）

#### ToolRegistry（工具注册表）

`registry.py` 维护 Agent → Tool 白名单，执行前做权限校验：

```
AGENT_TOOLS: Dict[str, List[str]] = {
    "novel_steward": [
        "load_project", "create_project", "delete_project",
        "edit_artifact", "generate_image", "update_exploration_level",
        "onboarding_propose_step", "onboarding_user_confirm",
        "onboarding_generate_chapter", "delegate_to_agent",
        "dispatch_background_task",
    ],
    "novel_writer": [
        "load_project", "read_chapter",
        "generate_chapter", "summarize_chapter",
    ],
    "world_tree_manager": [
        "load_project", "edit_artifact", "update_base",
        "weave_plot", "introspect_character", "adjust_style", "switch_pov",
    ],
}
```

#### 工具清单（15 个）

| 类别 | 工具名 | 文件 | 说明 |
|------|--------|------|------|
| 项目 | `load_project` | `project_tools.py` | 加载项目详情（含7件基座） |
| 项目 | `create_project` | `project_tools.py` | 创建新项目 |
| 项目 | `delete_project` | `project_tools.py` | 软删除项目（危险） |
| 章节 | `generate_chapter` | `chapter_tools.py` | 生成下一章，写文件+入DB |
| 章节 | `read_chapter` | `chapter_tools.py` | 读取指定章节正文 |
| 章节 | `summarize_chapter` | `summarize_chapter_tool.py` | 抽取一句话 summary |
| 基座 | `edit_artifact` | `edit_artifact_tool.py` | 7件基座轻量字段修改 |
| 基座 | `update_base` | `base_edit_tools.py` | 批量更新基座字段 |
| 基座 | `rollback_base` | `base_edit_tools.py` | 回滚基座到指定版本 |
| 情节 | `weave_plot` | `plot_tools.py` | 织入/调整主线支线走向 |
| 角色 | `introspect_character` | `character_tools.py` | 角色内心独白/分析 |
| 风格 | `adjust_style` | `style_tools.py` | 调整文风宪法 |
| 视角 | `switch_pov` | `pov_tools.py` | 切换叙事视角 |
| 图片 | `generate_image` | `image_tools.py` | 生成封面图（Gemini） |
| Onboarding | `onboarding_propose_step` | `onboarding_tools.py` | 提议 Onboarding 步骤 |
| Onboarding | `onboarding_user_confirm` | `onboarding_tools.py` | 用户确认，写入基座 |
| Onboarding | `onboarding_generate_chapter` | `onboarding_tools.py` | 生成第 1 章 |
| 委托 | `delegate_to_agent` | `delegation_tools.py` | 同步委托专家 Agent |
| 委托 | `dispatch_background_task` | `delegation_tools.py` | 异步派发后台任务 |

#### BaseTool 接口

```
class BaseTool(ABC):
    name: str            # tool name（OpenAI function name）
    description: str     # 给 LLM 看的描述
    input_schema: type[BaseModel]  # Pydantic 输入 schema

    @abstractmethod
    async def run(self, input: BaseModel) -> BaseModel | ToolError:
        ...

    def is_dangerous(self) -> bool:
        return False  # 危险工具返回 True
```

### 4.5 Onboarding 5 步流程（`agent/onboarding/`）

新建项目的引导式对话，管家通过 ReAct loop 推进：

```
★ 第一阶段：信息收集（不调任何工具）
  收集 6 个维度：项目名称 / 世界树基础 / 故事核心 / 主要角色 / 主线大纲 / 笔风标签
  收集完后展示确认清单，等用户明确确认

★ 第二阶段：一次性推完（用户确认后流水执行）
  1. create_project → project_id
  2. onboarding_propose_step(step=1) → 题材/风格/基调
  3. onboarding_propose_step(step=2) → palette
  4. onboarding_propose_step(step=3) + onboarding_user_confirm(step=3) → 故事核心
  5. onboarding_propose_step(step=4) + onboarding_user_confirm(step=4) → 完整大纲
  6. onboarding_generate_chapter → 生成第 1 章（同步，约 60-100s）
  7. dispatch_background_task(generate_cover) → 后台封面（不阻塞）
```

**状态持久化**：`onboarding_state` 表（每步 upsert，进程重启可续）

### 4.6 上下文组装（`agent/context/`）

根据不同 Agent 的视角裁剪 LLM messages：

| 函数 | 说明 |
|------|------|
| `build_messages_for_steward` | 管家上下文（用户历史 + 当前项目摘要） |
| `build_messages_for_chapter_generator` | 文笔家上下文（7件基座 + 最近N章summary） |
| `build_messages_for_worldtree_keeper` | 世界树上下文（7件基座 + 历史干预） |
| `build_messages_for_onboarding_step3` | Onboarding Step 3 上下文 |
| `build_messages_for_onboarding_step4` | Onboarding Step 4 上下文 |
| `load_chat_history` | 从 DB 加载对话历史（7+15 轮分层） |

### 4.7 Prompt 系统（`agent/prompts/`）

| 文件 | 内容 |
|------|------|
| `writing_laws.py` | 写作铁律（不可突破的底线，防止AI偷懒/跳戏/OOC） |
| `style_packs.py` | 风格包（爽文/严肃/轻松等对应的 Prompt 指导） |
| `specialists.py` | 专家 Prompt（WorldTree/Chapter/Memory Specialist） |
| `onboarding.py` | Onboarding Step 3/4 Prompt |
| `agent_prompt_factory.py` | Prompt 工厂（组装最终发送给 LLM 的完整 Prompt） |

---

## 5. Service 层

业务编排层，协调 `agent/` 和 `persistence/` 完成复合业务操作。

| 文件 | 职责 |
|------|------|
| `project_manager.py` | 项目 CRUD + 软删除（移到 `.trash/`）+ 回档（删后续章节 + 更新索引） |
| `onboarding_flow.py` | Onboarding 5 步状态机（状态读写走 DB） |
| `onboarding_artifacts.py` | 7 件基座 Pydantic 拼装（step payload → WorldTreeRow 等） |
| `consistency_checker.py` | 基座一致性检查（干预后检查逻辑是否冲突） |
| `cover_image_generator.py` | 封面图生成（调 LLMAdapter → GeminiProvider，保存到 `data/projects/{id}/cover.png`） |
| `intervention_parser.py` | 干预指令解析（自然语言 → 结构化干预 payload） |

---

## 6. Adapter 层

外部服务适配，隔离 LLM 协议差异。

### LLM Adapter 统一入口（`adapters/llm_adapter.py`）

业务代码只调 `LLMAdapter`，不直连 LLM：

```
adapter = get_llm_adapter()

# 同步对话（带重试）
response = await adapter.complete(LLMRequest(...))

# 多轮对话便捷调用
response = await adapter.complete_with_messages(
    messages=[{"role": "user", "content": "..."}],
    system_prompt="...",
    temperature=0.85,
    max_tokens=8192,
    enable_thinking=True,    # DeepSeek thinking 模式
    frequency_penalty=0.3,   # 探索度旋钮
)

# 流式调用（章节生成）
async for chunk in adapter.stream(LLMRequest(...)):
    ...

# 图片生成（Gemini）
result = await adapter.generate_image(prompt, aspect_ratio="16:9")
```

### LLM Router（`adapters/llm_router.py`）

根据 `ModelRole` 将请求路由到对应 Provider：

| ModelRole | Provider | 协议 |
|-----------|----------|------|
| `TEXT` | DeepSeekProvider | OpenAI 兼容（HTTP POST） |
| `IMAGE` | GeminiProvider | Google Native（提交 + 轮询） |

### 重试机制（`adapters/retry.py`）

指数退避重试，默认 3 次，基础延迟 1.0s：

```
await with_retry(provider.complete, request, max_retries=3, base_delay=1.0)
```

### Provider 实现

**DeepSeekProvider**（`adapters/providers/deepseek.py`）：
- OpenAI 兼容协议，通过 Friday AI 网关代理
- 支持 `enable_thinking` 参数（DeepSeek 推理链）
- 支持 `tool_calls`（function calling）

**GeminiProvider**（`adapters/providers/gemini.py`）：
- Google Native 协议（图片生成）
- 异步提交 → 轮询查询（最长 120s）
- 返回 base64 图片数据，业务层负责保存

---

## 7. 领域核心层

`core/` 是零外部依赖的领域模型，任何层都可安全 import。

### WorldTree 聚合根（`core/world_tree.py`）

```
class WorldTree:
    world_tree: WorldTreeSchema
    style_charter: StyleCharter
    genre_resonance: GenreResonance
    main_plot: MainPlot
    sub_plots: List[SubPlot]
    character_card: CharacterCard
    seed_table: SeedTable
```

7 件基座的内存聚合，提供：
- `to_prompt_context()` → 生成 LLM 上下文文本
- `diff(other)` → 计算两个版本的 diff
- `validate_consistency()` → 一致性校验

### 7 件基座 Schema（`core/schemas/`）

| Schema | 字段摘要 |
|--------|---------|
| `WorldTreeSchema` | timeline_era, anchor_event, geography, core_rules |
| `StyleCharter` | voice, pacing, literary_reference, writing_rules |
| `GenreResonance` | accept[], reject[], anchors[] |
| `MainPlot` | arc_phrase, beats[], current_beat |
| `SubPlot` | title, description, status, priority, linked_seeds |
| `CharacterCard` | characters[], relationships[] |
| `SeedTable` | seeds[]（含 importance/size/orientation/status） |

### EventBus（`core/event_bus.py`）

领域事件总线，用于解耦组件间通信：

```
bus = get_event_bus()

# 订阅
@bus.on("onboarding.step4.completed")
async def on_step4_done(event: dict):
    await generate_cover_image(event["project_id"])

# 发布
await bus.emit("onboarding.step4.completed", {"project_id": project_id})
```

Onboarding Step 4 完成后，`hooks.py` 通过 EventBus 订阅，自动触发封面图生成。

### 异常层级（`core/exceptions.py`）

```
RealtimeNovelError (基类)
├── ProjectNotFoundError
├── ChapterNotFoundError
├── OnboardingError
│   └── OnboardingStepError
├── LLMError
│   ├── LLMTimeoutError
│   └── LLMRateLimitError
└── ConsistencyError
```

---

## 8. 配置系统

### `backend/config/agents.json`

唯一配置文件，控制：

1. **模型池**：每个模型的协议/URL/默认参数
2. **Agent → 模型映射**：哪个 Agent 用哪个模型
3. **探索度档位**：conservative/standard/wild 的 temperature/max_tokens/frequency_penalty

```json
{
  "exploration_levels": {
    "conservative": {
      "temperature": 0.6,
      "max_tokens": 8192,
      "frequency_penalty": 0.1,
      "supplement_aggressiveness": "low",
      "chapter_word_count": 5000
    }
  },
  "models": {
    "friday/deepseek-v4-pro-tencent": {
      "protocol": "openai_compat",
      "base_url": "https://aigc.sankuai.com/v1/openai/native",
      "model_id": "deepseek-v4-pro-tencent",
      "supports_thinking": true
    }
  },
  "agents": {
    "NovelSteward": {"model": "friday/deepseek-v4-pro-tencent"}
  }
}
```

### `.llm_api_key`（gitignored）

```json
{"FRIDAY_API_KEY": "your_api_key_here"}
```

`config_loader.py` 在启动时读取，注入到 Provider 的 HTTP Header。

---

## 9. 日志系统

`backend/utils/logger.py` 提供两种使用方式：

**`@logger` 类装饰器**：为类注入 `self.log`，方法名自动追踪：

```
from backend.utils.logger import logger

@logger
class NovelSteward:
    async def receive(self, ...):
        self.log.info("NovelSteward.receive START: user_id=%s", user_id)
        # ...
        self.log.error("发生错误: %s", e, exc_info=True)
```

**直接 import**：

```
import logging
log = logging.getLogger(__name__)
log.info("...")
```

**日志输出**：
- 开发模式（`--reload`）：直接输出到 stdout
- 生产模式（`start.sh`）：输出到 `tmp/logs/backend.log`

**LLM Prompt 调试日志**：

```bash
LLM_PROMPT_LOG=1 uvicorn backend.api.app:app --port 7778
```

开启后，每次 LLM 调用前打印完整 messages（含 system / user / assistant / tool 全部轮次）。

