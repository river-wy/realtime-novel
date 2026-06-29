# Realtime Novel

**实时生成 + 可干预的小说阅读产品**

读者可在阅读过程中介入剧情走向：干预角色选择、回档到任意章节、调整创作风格。AI 在世界树（七件基座）约束下实时续写，保持故事内在一致性。

---

## 目录

- [产品是什么](#产品是什么)
- [技术架构](#技术架构)
- [工程结构](#工程结构)
- [快速开始](#快速开始)
- [API 文档](#api-文档)
- [配置说明](#配置说明)
- [开发指南](#开发指南)

---

## 产品是什么

### 核心概念

**世界树（7 件基座）**：每个小说项目都有 7 份结构化设定文档，共同约束 AI 创作范围：

| 件 | 内容 |
|----|------|
| World Tree | 时间线、地理、核心规则 |
| Style Charter | 写作风格、文学参照 |
| Genre Resonance | 题材、情绪基调 |
| Main Plot | 主线弧线、剧情节点 |
| Sub Plots | 支线故事 |
| Character Card | 角色卡（含关系网络） |
| Seed Table | 伏笔种子（埋下→触发机制） |

**管家 Agent（NovelSteward）**：用户唯一入口。所有消息（首页聊天 / 项目内聊天 / 创建项目 / 闲聊）都先由管家接收，管家通过 ReAct loop 自主决定调用工具还是委托专家 Agent。

**Onboarding 引导**：新建项目时，管家通过多轮对话引导用户逐步填写 7 件基座，信息齐全后自动一次性生成完整设定 + 第 1 章。

**探索度（Exploration Level）**：项目级开关，控制 AI 的发挥空间：

| 档位 | 描述 | temperature | 字数 |
|------|------|-------------|------|
| `conservative` | 严守用户输入，AI 补充少 | 0.6 | 5000 字/章 |
| `standard` | 平衡模式（默认） | 0.85 | 5000 字/章 |
| `wild` | 鼓励扩展，AI 补充发散 | 1.05 | 5000 字/章 |

**干预与回档**：每章生成前可提交干预指令；支持回档到任意历史章节重新走向。

---

## 技术架构

```
浏览器（Vue 3 + TypeScript）
    │ HTTP REST + WebSocket
    ▼
后端 FastAPI（Python 3.12）
    ├── api/          HTTP 路由 + WS /api/chat 端点
    ├── agent/        LLM Agent ReAct 引擎 + 专家 + 工具
    ├── services/     业务编排层（Onboarding / 项目管理等）
    ├── persistence/  SQLite CRUD（WAL 模式 + 自动迁移）
    ├── adapters/     LLM 多 Provider 适配（DeepSeek / Gemini）
    ├── core/         领域 Schema（零外部依赖）
    └── config/       模型路由 + 探索度配置（agents.json）
```

**分层依赖方向**（严格单向）：
```
api → services → agent → persistence → adapters
                    ↑
                   core（零依赖，任何层都可 import）
```

**LLM**：通过美团 Friday AI 网关接入：
- 文本生成：`friday/deepseek-v4-pro-tencent`（OpenAI 兼容协议）
- 图片生成：`friday/gemini-3.1-flash-image-preview`（Google Native 协议）

**Agent 架构**（ReAct）：
```
用户消息（WebSocket）
    ↓
NovelSteward（管家，唯一入口）
    ├── ReAct loop（自主调工具）
    │     ├── 项目 CRUD、Onboarding、基座编辑、图片生成
    │     └── delegate_to_agent → 同步委托专家
    │
    ├── NovelWriter（文笔家）
    │     └── 生成章节正文 + summary + 落盘
    │
    └── WorldTreeManager（世界树管理）
          └── 干预影响分析 + 基座一致性检查 + 种子预留
```

---

## 工程结构

```
realtime-novel/
├── backend/                       # Python 后端包
│   ├── api/                       # FastAPI 路由层
│   │   ├── app.py                 # 应用工厂，CORS 配置，静态文件挂载
│   │   ├── ws_manager.py          # WS /api/chat 端点 + WebSocketManager
│   │   ├── project_routes.py      # 项目 CRUD（GET/POST/DELETE/PATCH）
│   │   ├── chapter_routes.py      # 章节读取 / 生成
│   │   ├── action_routes.py       # onboarding / 干预 / 回档 / 图片 / 基座修改
│   │   └── system_routes.py       # /api/health, /api/info
│   │
│   ├── agent/                     # LLM Agent 大脑
│   │   ├── agents/                # 3 顶层 Agent
│   │   │   ├── novel_steward.py   # 管家（唯一用户入口，ReAct loop）
│   │   │   ├── novel_writer.py    # 文笔家（章节正文生成）
│   │   │   └── world_tree_manager.py  # 世界树管理（基座一致性）
│   │   ├── runtime/               # ReAct 引擎
│   │   │   ├── executor.py        # AgentExecutor ReAct loop + Middleware
│   │   │   └── session_cache.py   # 进程内 session cache（多轮对话复用）
│   │   ├── onboarding/            # Onboarding 5 步流程
│   │   │   ├── controller.py      # Step 3/4 LLM 推演
│   │   │   └── hooks.py           # 事件总线订阅（完成后生成封面等）
│   │   ├── specialists/           # 内部专家工具
│   │   │   ├── exploration.py     # 探索度参数查询
│   │   │   └── chapter_summarizer.py  # 章节 summary 抽取
│   │   ├── context/               # 上下文组装
│   │   │   ├── builders.py        # 3 角色 messages 拼装
│   │   │   ├── onboarding_builders.py # Onboarding Step 3/4 messages
│   │   │   └── _helpers.py        # DB 数据格式化 helper
│   │   ├── prompts/               # Prompt 模板集中
│   │   │   ├── writing_laws.py    # 写作规则（不可突破的底线）
│   │   │   ├── style_packs.py     # 风格包 Prompt
│   │   │   ├── specialists.py     # 专家 Prompt（WorldTree/Chapter/Memory）
│   │   │   └── onboarding.py      # Onboarding Step 3/4 Prompt
│   │   └── tools/                 # 15 个工具（ToolRegistry 管理）
│   │       ├── registry.py        # Agent→Tool 白名单 + OpenAI schema 转换
│   │       ├── delegation_tools.py # delegate_to_agent + dispatch_background_task
│   │       ├── chapter_tools.py   # generate_chapter + read_chapter
│   │       ├── project_tools.py   # load/create/delete_project
│   │       ├── image_tools.py     # generate_image（Gemini）
│   │       ├── onboarding_tools.py # onboarding_propose_step/confirm/generate
│   │       ├── edit_artifact_tool.py # edit_artifact（7 件基座轻量修改）
│   │       ├── plot_tools.py      # weave_plot
│   │       ├── character_tools.py # introspect_character
│   │       ├── style_tools.py     # adjust_style
│   │       ├── pov_tools.py       # switch_pov
│   │       └── base_edit_tools.py # update_base + rollback_base
│   │
│   ├── services/                  # 业务编排层
│   │   ├── project_manager.py     # 项目 CRUD + 软删除 + 回档
│   │   ├── onboarding_flow.py     # Onboarding 5 步状态机
│   │   ├── onboarding_artifacts.py # 7 件基座 Pydantic 拼装
│   │   ├── consistency_checker.py # 基座一致性检查
│   │   ├── cover_image_generator.py # 封面图生成（Gemini）
│   │   └── intervention_parser.py # 干预指令解析
│   │
│   ├── persistence/               # SQLite 数据访问层
│   │   ├── sqlite_store.py        # 连接管理 + WAL + 自动迁移
│   │   ├── models.py              # 所有表的 Pydantic Row Model
│   │   ├── migrations/v001_init.sql  # 合并版初始 Schema（19 张表）
│   │   ├── project_repository.py  # projects + 7 件基座 CRUD
│   │   ├── chapter_repository.py  # chapters CRUD + 正文文件读写
│   │   ├── conversation_repository.py # conversations + messages
│   │   ├── onboarding_repository.py   # onboarding_state
│   │   ├── chapter_status_repository.py # chapter_status（生成状态）
│   │   ├── tool_call_log_repository.py  # tool_calls_log（审计）
│   │   ├── project_deleted_repository.py # 软删除记录
│   │   └── user_preference_repository.py # 用户偏好
│   │
│   ├── adapters/                  # 外部服务适配
│   │   ├── llm_adapter.py         # LLMAdapter 统一入口（complete/stream/image）
│   │   ├── llm_router.py          # model_role → Provider 路由
│   │   ├── streaming.py           # 流式回调封装
│   │   ├── retry.py               # 指数退避重试（3 次）
│   │   ├── types.py               # LLMRequest/LLMResponse 数据类
│   │   └── providers/
│   │       ├── deepseek.py        # DeepSeek（OpenAI 兼容协议）
│   │       └── gemini.py          # Gemini（Google Native + 图片生成）
│   │
│   ├── core/                      # 领域模型（零外部依赖）
│   │   ├── world_tree.py          # WorldTree 内存聚合根
│   │   ├── exceptions.py          # 异常层级
│   │   ├── event_bus.py           # 领域事件总线
│   │   └── schemas/               # 7 件基座 Pydantic Schema
│   │       ├── world_tree.py / style_charter.py / genre_resonance.py
│   │       ├── main_plot.py / sub_plot.py / character_card.py
│   │       ├── seed_table.py / chapter.py
│   │
│   ├── config/
│   │   ├── agents.json            # 模型池 + Agent→model 路由 + 探索度配置
│   │   └── config_loader.py       # .llm_api_key + agents.json 加载
│   │
│   └── utils/
│       ├── logger.py              # 结构化日志（@logger 装饰器）
│       └── version.py             # 版本号
│
├── frontend/                      # Vue 3 + TypeScript 前端
│   └── src/
│       ├── views/                 # 4 个页面
│       │   ├── Home.vue           # 首页（管家大厅，聊天 + 项目入口）
│       │   ├── World.vue          # 世界管理（项目信息 + 章节列表 + 回档/删除）
│       │   ├── Reader.vue         # 章节阅读（3 栏：导航/正文/干预）
│       │   └── WorldList.vue      # 项目列表页
│       ├── components/
│       │   └── ChatBox.vue        # 通用聊天组件（WS 连接 + 消息渲染）
│       ├── composables/
│       │   └── useStewardChat.ts  # 管家对话 composable（WS 状态管理）
│       ├── stores/                # Pinia 状态管理
│       │   ├── projects.ts        # 项目列表 / 当前项目
│       │   ├── chapters.ts        # 章节列表 / 当前章节 / 生成状态
│       │   └── conversation.ts    # 对话历史（首页聊天）
│       ├── api/                   # Axios 封装
│       │   ├── projects.ts        # 项目 CRUD API
│       │   ├── chapters.ts        # 章节 API
│       │   ├── actions.ts         # 干预 / 回档 / 图片 / 基座 API
│       │   └── client.ts          # Axios 实例配置
│       └── styles/                # 全局样式
│           ├── tokens.css         # CSS 变量（色彩/间距/字体/动效）
│           ├── base.css           # 全局基础样式 Reset
│           └── animations.css     # 动画关键帧
│
├── data/
│   ├── novel.db                   # SQLite 主数据库（gitignored）
│   └── projects/                  # 章节正文文件（gitignored）
│       └── {project_id}/chapters/chapter_NNN.md
│
├── scripts/
│   ├── start.sh                   # 一键启动前后端
│   └── stop.sh                    # 一键停止
│
├── tests/
│   └── e2e_integration_test.py    # E2E 集成测试
│
├── docs/                          # 技术文档
│   ├── backend/                   # 后端技术文档
│   └── frontend/                  # 前端技术文档
│
├── .spec/                         # 设计规格文档（里程碑规划）
├── pyproject.toml                 # Python 包配置（依赖 / 入口点）
├── CHANGELOG.md                   # 版本变更记录
└── .llm_api_key                   # LLM API Key（gitignored）
```

---

## 快速开始

### 前置要求

- Python ≥ 3.11
- Node.js ≥ 18
- 美团内网（Friday AI 网关访问）

### 1. 克隆 & 安装后端

```bash
git clone <repo>
cd realtime-novel

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖（editable 模式）
pip install -e .
```

### 2. 配置 LLM API Key

```bash
# 创建 .llm_api_key 文件（标准 JSON 格式）
echo '{"FRIDAY_API_KEY": "your_friday_api_key"}' > .llm_api_key
chmod 600 .llm_api_key
```

### 3. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 4. 一键启动

```bash
bash scripts/start.sh
```

启动后：

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:7777 |
| 后端 API | http://127.0.0.1:7778 |
| API 文档（Swagger） | http://127.0.0.1:7778/docs |
| 日志 | `tail -f tmp/logs/backend.log tmp/logs/frontend.log` |

```bash
# 停止
bash scripts/stop.sh
```

### 5. 手动分别启动（调试用）

```bash
# 后端
source .venv/bin/activate
uvicorn backend.api.app:app --host 127.0.0.1 --port 7778 --reload

# 前端（另开终端）
cd frontend
npm run dev -- --port 7777
```

---

## API 文档

完整 OpenAPI 文档启动后访问 `http://127.0.0.1:7778/docs`。

### WebSocket

| 端点 | 说明 |
|------|------|
| `WS /api/chat` | 主对话端点（所有用户消息统一入口） |

**客户端发送消息格式**：
```
{"type": "user_message", "content": "...", "project_id": "可选"}
{"type": "interrupt"}
{"type": "ping"}
```

**服务端推送事件**：
```
{"type": "agent_thinking", "content": "..."}
{"type": "tool_result", "tool": "...", "result": {}, "status": "success"}
{"type": "agent_message", "content": "...", "structured_data": {}}
{"type": "confirm_required", "action": "delete_project", "details": {}}
{"type": "error", "code": "...", "message": "..."}
```

### 项目管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/projects` | 列出所有项目 |
| `POST` | `/api/projects` | 创建项目 |
| `GET` | `/api/projects/{id}` | 获取项目详情（含 7 件基座） |
| `DELETE` | `/api/projects/{id}?confirm=true` | 软删除项目（移入 .trash/） |
| `PATCH` | `/api/projects/{id}/exploration-level` | 切换探索度 |

### 章节

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/projects/{id}/chapters` | 章节列表（含 title/summary/word_count） |
| `GET` | `/api/projects/{id}/chapters/{n}` | 读取第 n 章正文 |
| `POST` | `/api/projects/{id}/chapters` | 生成下一章（含干预参数） |

### 操作

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/projects/{id}/interventions` | 提交剧情干预 |
| `POST` | `/api/projects/{id}/rollback?to_chapter=N&confirm=true` | 回档到第 N 章 |
| `POST` | `/api/projects/{id}/image` | 生成封面图（Gemini） |
| `PATCH` | `/api/projects/{id}/base` | 修改 7 件基座某件 |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/info` | 版本信息 + 已加载模型 |

---

## 配置说明

### `.llm_api_key`（必填，gitignored）

```json
{
  "FRIDAY_API_KEY": "your_friday_api_key_here"
}
```

文件权限建议 `chmod 600`。

### `backend/config/agents.json`

控制模型路由和探索度参数，**已入库，无需修改**除非要换模型：

```
{
  "models": {
    "friday/deepseek-v4-pro-tencent": {
      "protocol": "openai_compat",
      "base_url": "https://aigc.sankuai.com/v1/openai/native",
      "supports_thinking": true
    },
    "friday/gemini-3.1-flash-image-preview": {
      "protocol": "google_native"
    }
  },
  "agents": {
    "NovelSteward":               { "model": "friday/deepseek-v4-pro-tencent" },
    "ChapterGeneratorSpecialist": { "model": "friday/deepseek-v4-pro-tencent" },
    "ImageGeneratorStub":         { "model": "friday/gemini-3.1-flash-image-preview" }
  },
  "exploration_levels": {
    "conservative": { "temperature": 0.6,  "max_tokens": 8192 },
    "standard":     { "temperature": 0.85, "max_tokens": 8192 },
    "wild":         { "temperature": 1.05, "max_tokens": 8192 }
  }
}
```

### 端口

默认端口硬编码在 `scripts/start.sh`，如需修改同步更新 `frontend/vite.config.ts`：

| 服务 | 默认端口 |
|------|---------|
| 前端 dev server | `7777` |
| 后端 API | `7778` |

### 环境变量（可选）

| 变量 | 默认 | 说明 |
|------|------|------|
| `LLM_PROMPT_LOG` | `0` | 设为 `1` 开启完整 LLM prompt 日志（调试用） |
| `LOG_LEVEL` | `INFO` | 日志级别 |

---

## 开发指南

### 目录约定

| 层 | 允许 import | 禁止 import |
|---|---|---|
| `backend/core/` | 标准库、pydantic | 其他任何层 |
| `backend/adapters/` | core | services/agent/api |
| `backend/persistence/` | core、adapters | services/agent/api |
| `backend/agent/` | core、persistence、adapters | services/api |
| `backend/services/` | core、persistence、agent | api |
| `backend/api/` | 全部 | — |

### 数据库迁移

```bash
# 新增迁移脚本放在 backend/persistence/migrations/
# 命名规则：v002_description.sql
# SQLiteStore 启动时自动按版本号升序执行未跑过的迁移
```

### 新增 Agent 工具

1. 在 `backend/agent/tools/` 新建 `my_tool.py`，继承 `BaseTool`
2. 文件末尾调 `register_tool(MyTool())`
3. 在 `backend/agent/tools/registry.py` 的 `AGENT_TOOLS` 字典里，加入目标 Agent 的工具列表
4. 在 `backend/agent/tools/__init__.py` 中 import 新文件（触发注册）

### 运行测试

```bash
source .venv/bin/activate
pytest tests/ -v
```

### E2E 集成测试

```bash
python tests/e2e_integration_test.py
```

### 日志

后端使用结构化日志（`backend/utils/logger.py`）：
- 生产模式：输出到 `tmp/logs/backend.log`
- 开发模式（`--reload`）：直接输出到控制台
- 开启 LLM Prompt 完整日志：`LLM_PROMPT_LOG=1 uvicorn ...`

---

## 版本

当前版本：**v0.9.x**（含完整 Agent 架构、Onboarding 流程、章节生成、干预回档、封面图生成）

详细变更记录见 [`CHANGELOG.md`](CHANGELOG.md)。

详细技术文档见 [`docs/`](docs/)：
- [后端架构文档](docs/backend/architecture.md)
- [后端数据存储文档](docs/backend/persistence.md)
- [前端技术文档](docs/frontend/overview.md)
