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

**Onboarding 5 步引导**：新建项目时，AI 通过 WebSocket 对话引导用户逐步填写 7 件基座。

**探索度（Exploration Level）**：项目级开关，控制 AI 的发挥空间：
- `conservative`：严守用户输入，字数克制
- `standard`：平衡模式（默认）
- `wild`：鼓励扩展，字数上限放宽 20%

**干预与回档**：每章生成前可提交干预指令；支持回档到任意历史章节重新走向。

---

## 技术架构

```
浏览器（Vue 3）
    │ HTTP + WebSocket
    ▼
后端 FastAPI（Python 3.12）
    ├── api/          HTTP 路由 + WS 端点
    ├── agent/        LLM Agent 状态机 + 专家 + 工具
    ├── services/     业务编排层
    ├── persistence/  SQLite CRUD（sqlite-vec）
    ├── adapters/     LLM 多 Provider 适配
    ├── core/         领域 Schema（零外部依赖）
    └── config/       模型路由 + 探索度配置
```

**分层依赖方向**：`api → services → agent → persistence → adapters`，`core` 无依赖。

**LLM**：通过美团 Friday AI 网关接入，默认模型 `deepseek-v4-pro-tencent`（文本）+ `gemini-3.1-flash-image-preview`（图片生成）。

---

## 工程结构

```
realtime-novel/
├── backend/                   # Python 后端包
│   ├── api/                   # FastAPI 路由层
│   │   ├── app.py             # 应用工厂，CORS 配置
│   │   ├── ws_manager.py      # WS /api/chat + Onboarding WS 处理器
│   │   ├── project_routes.py  # GET/POST/DELETE /api/projects
│   │   ├── chapter_routes.py  # GET/POST /api/projects/{id}/chapters
│   │   ├── action_routes.py   # POST onboarding/interventions/rollback/image/base
│   │   ├── system_routes.py   # GET /api/health, /api/info
│   │   └── schemas/events.py  # WS 事件 Pydantic Schema
│   ├── agent/                 # LLM Agent 大脑
│   │   ├── state.py           # AgentState / Intent / ToolCall（Pydantic）
│   │   ├── state_graph.py     # 6 节点状态机（intake→consult→plan→act→reflect→respond）
│   │   ├── nodes.py           # 6 个节点函数
│   │   ├── specialists.py     # 3 个专家 Agent（Chapter / WorldTree / Memory）
│   │   ├── onboarding_agent.py# Step 3/4 引导式对话
│   │   ├── context_builder.py # 多轮上下文组装（DB → LLM messages）
│   │   ├── prompts.py         # 所有 Prompt 模板
│   │   ├── exploration.py     # 探索度工具函数（LLM 参数 / 风格指导 / Prompt 填充）
│   │   ├── style_inference.py # 风格推断（题材→风格宪法）
│   │   ├── chapter_summarizer.py # 章节 summary sentinel 解析
│   │   ├── state_graph_stub.py# 章节生成委托（调 ChapterGeneratorSpecialist）
│   │   └── tools/             # 13 个工具（chapter/plot/character/style/memory/image/pov…）
│   ├── services/              # 业务编排
│   │   ├── async_project_manager.py   # 项目 CRUD + 软删除 + 回档
│   │   ├── async_onboarding_flow.py   # Onboarding 5 步状态机
│   │   ├── async_intervention_parser.py# 干预写入
│   │   ├── async_rollback_manager.py  # 回档委托
│   │   ├── async_chapter_generator.py # 章节生成委托
│   │   ├── onboarding_artifacts.py    # 7 件基座拼装
│   │   └── async_wrappers.py          # 向后兼容转发层
│   ├── persistence/           # SQLite 数据访问
│   │   ├── sqlite_store.py    # 连接管理 + WAL + 迁移
│   │   ├── models.py          # 所有表的 Pydantic Row Model
│   │   ├── project_repository.py      # projects + 7 件基座 CRUD
│   │   ├── chapter_repository.py      # chapters CRUD
│   │   ├── conversation_store.py      # conversations + messages CRUD
│   │   └── migrations/        # SQLite 迁移脚本（v001–v004）
│   ├── adapters/              # 外部服务适配
│   │   ├── llm_adapter.py     # 统一入口（complete / stream / generate_image）
│   │   ├── llm_router.py      # model_name → Provider 路由
│   │   ├── providers/deepseek.py  # DeepSeek（OpenAI 兼容）
│   │   └── providers/gemini.py    # Gemini（原生异步 + 图片生成）
│   ├── core/                  # 领域模型（零外部依赖）
│   │   ├── world_tree.py      # WorldTree 内存聚合
│   │   ├── exceptions.py      # 异常层级
│   │   └── schemas/           # 7 件 + ChapterSummary Pydantic Schema
│   └── config/
│       ├── agents.json        # 模型池 + Agent→model 路由 + 探索度配置
│       └── config_loader.py   # .llm_api_key + agents.json 加载
├── frontend/                  # Vue 3 + TypeScript 前端
│   └── src/
│       ├── views/             # Home / Onboarding / World / Reader
│       ├── api/               # Axios 封装（projects / chapters / actions）
│       ├── stores/            # Pinia stores（projects / chapters / conversation）
│       └── composables/       # useOnboardingChat（WS 状态管理）
├── data/
│   ├── novel.db               # SQLite 主数据库（gitignored）
│   └── projects/              # 章节文件（gitignored）
├── scripts/
│   ├── start.sh               # 一键启动前后端
│   └── stop.sh                # 一键停止
├── .llm_api_key               # LLM API Key（gitignored，见配置说明）
└── pyproject.toml
```

---

## 快速开始

### 前置要求

- Python ≥ 3.12
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
- **前端**：http://localhost:7777
- **后端 API**：http://127.0.0.1:7778
- **API 文档（Swagger）**：http://127.0.0.1:7778/docs
- **日志**：`tail -f tmp/logs/backend.log tmp/logs/frontend.log`

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

完整 OpenAPI 文档启动后访问 `http://127.0.0.1:7778/docs`。主要端点：

### 项目管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/projects` | 列出所有项目 |
| `POST` | `/api/projects` | 创建项目 |
| `GET` | `/api/projects/{id}` | 获取项目详情（含 7 件基座） |
| `DELETE` | `/api/projects/{id}?confirm=true` | 软删除项目（移入 trash） |
| `PATCH` | `/api/projects/{id}/exploration-level` | 切换探索度 |

### 章节

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/projects/{id}/chapters` | 章节列表 |
| `GET` | `/api/projects/{id}/chapters/{n}` | 读取第 n 章正文 |
| `POST` | `/api/projects/{id}/chapters` | 生成下一章（含干预参数） |

### 操作

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/projects/{id}/onboarding` | Onboarding 步骤提交（Step 1-5） |
| `POST` | `/api/projects/{id}/interventions` | 提交剧情干预 |
| `POST` | `/api/projects/{id}/rollback?to_chapter=N&confirm=true` | 回档到第 N 章 |
| `POST` | `/api/projects/{id}/image` | 生成主立绘（Gemini） |
| `PATCH` | `/api/projects/{id}/base` | 修改 7 件基座某件 |

### WebSocket

| 端点 | 说明 |
|------|------|
| `WS /api/chat` | 主对话端点（user_message / interrupt / onboarding_request_proposal / onboarding_confirm） |

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
// backend/config/agents.json（简略）
{
  "models": {
    "friday/deepseek-v4-pro-tencent": { "protocol": "openai_compat", ... },
    "friday/gemini-3.1-flash-image-preview": { "protocol": "google_native", ... }
  },
  "agents": {
    "OnboardingAgent":            { "model": "friday/deepseek-v4-pro-tencent" },
    "ChapterGeneratorSpecialist": { "model": "friday/deepseek-v4-pro-tencent" },
    "ImageGeneratorAgent":        { "model": "friday/gemini-3.1-flash-image-preview" }
  },
  "exploration_levels": {
    "conservative": { "temperature": 0.6,  "max_tokens": 2500 },
    "standard":     { "temperature": 0.85, "max_tokens": 4500 },
    "wild":         { "temperature": 1.05, "max_tokens": 6000 }
  }
}
```

### 端口

默认端口硬编码在 `scripts/start.sh`，如需修改同步更新 `frontend/vite.config.ts`：

| 服务 | 默认端口 |
|------|---------|
| 前端 dev server | `7777` |
| 后端 API | `7778` |

---

## 开发指南

### 目录约定

- **`backend/core/`**：零外部依赖，只放 Pydantic Schema 和领域模型，不 import 其他层
- **`backend/agent/`**：允许 import `persistence`（读数据）和 `adapters`（调 LLM），不 import `services`
- **`backend/services/`**：编排层，可调 `agent` 和 `persistence`
- **`backend/api/`**：薄路由，只做 HTTP 序列化/反序列化，业务逻辑委托给 `services`

### 数据库迁移

```bash
# 新增迁移脚本放在 backend/persistence/migrations/
# 命名规则：v005_description.sql
# SQLiteStore 启动时自动按版本号升序执行未跑过的迁移
```

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

后端使用结构化日志（`backend/utils/logger.py`），生产模式输出到 `tmp/logs/backend.log`，开发模式（`--reload`）直接输出到控制台。

---

## 版本

当前版本：**v0.3.0-alpha**（含前后端、完整 Onboarding 流程、章节生成、干预回档）

详细变更记录见 [`CHANGELOG.md`](CHANGELOG.md)。
