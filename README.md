# Realtime Novel

**实时生成 + 可干预的小说阅读产品**

读者可在阅读过程中介入剧情走向：干预角色选择、回档到任意章节、调整创作风格。AI 在世界树（七件基座）约束下实时续写，保持故事内在一致性。

---

## 是什么

**核心概念**：

- **世界树（7 件基座）** — 每个项目都有 7 份结构化设定（World Tree / Style Charter / Genre Resonance / Main Plot / Sub Plots / Character Card / Seed Table），共同约束 AI 创作范围
- **管家 Agent（NovelSteward）** — 用户唯一入口。所有消息（首页聊天 / 项目内聊天 / 创建项目 / 闲聊）都先由管家接收，通过 ReAct loop 自主决定调工具还是委托专家 Agent
- **3 专家 Agent** — NovelWriter 生成章节正文；WorldTreeManager 维护基座一致性与干预影响；Validator 审核章节质量（v0.9 新增）
- **Onboarding 引导** — 新建项目时管家通过多轮对话引导填写 7 件基座，信息齐全后自动生成完整设定 + 第 1 章
- **探索度（Exploration Level）** — `conservative` / `standard` / `wild` 三档，控制 AI 发挥空间
- **干预与回档** — 每章生成前可提交干预指令；支持回档到任意历史章节重新走向

**Web 端** + **HTTP REST + WebSocket** + **ReAct LLM 引擎** + **SQLite 持久化** + **Friday AI 网关**（DeepSeek 文本 / Gemini 图片）

---

## 进度

当前版本 **v0.9.6**（commit `e717e5b`）。

完整里程碑见 [CHANGELOG.md](./CHANGELOG.md)。最近几个关键节点：

- v0.6 管家化重构 — 单一入口 Agent 取代分散意图识别
- v0.7 删 3 个 Onboarding 工具 — 收归管家
- v0.9 Validator 引入 — 文笔家后置审核
- v0.9.5 Volume 增强 — 章节卷总结 + WTM（World Tree Manager）方法扩展

---

## 从哪看

| 你想知道什么 | 看哪里 |
|---|---|
| 后端整体架构、分层、依赖规则 | [docs/backend/architecture.md](./docs/backend/architecture.md) |
| 后端 Agent 系统（管家 / 文笔家 / 架构师 / Validator） | [docs/backend/agent.md](./docs/backend/agent.md) |
| 后端数据存储（SQLite 19 张表） | [docs/backend/persistence.md](./docs/backend/persistence.md) |
| 后端业务编排层 | [docs/backend/services.md](./docs/backend/services.md) |
| 后端 LLM 适配（DeepSeek / Gemini） | [docs/backend/adapters.md](./docs/backend/adapters.md) |
| 后端领域核心（WorldTree + 7 件基座） | [docs/backend/core.md](./docs/backend/core.md) |
| 前端架构、路由、构建 | [docs/frontend/architecture.md](./docs/frontend/architecture.md) |
| 前端 API + WebSocket 集成 | [docs/frontend/api-integration.md](./docs/frontend/api-integration.md) |
| 前端状态管理（Pinia + Composable） | [docs/frontend/state-management.md](./docs/frontend/state-management.md) |
| 前端页面与组件 | [docs/frontend/pages-and-components.md](./docs/frontend/pages-and-components.md) |
| 前端样式系统 | [docs/frontend/styling.md](./docs/frontend/styling.md) |
| 前端构建与部署 | [docs/frontend/build-and-deploy.md](./docs/frontend/build-and-deploy.md) |
| 前端 API 对接自检报告 | [docs/frontend/api-self-check.md](./docs/frontend/api-self-check.md) |

---

## 怎么跑

### 前置要求

- Python ≥ 3.11
- Node.js ≥ 18
- 美团内网（Friday AI 网关访问）

### 1. 安装后端

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. 配置 LLM API Key

```bash
echo '{"FRIDAY_API_KEY": "your_friday_api_key"}' > .llm_api_key
chmod 600 .llm_api_key
```

### 3. 安装前端

```bash
cd frontend && npm install && cd ..
```

### 4. 一键启动

```bash
bash scripts/start.sh
```

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:7777 |
| 后端 API | http://127.0.0.1:7778 |
| Swagger | http://127.0.0.1:7778/docs |
| 日志 | `tail -f tmp/logs/backend.log tmp/logs/frontend.log` |

```bash
# 停止
bash scripts/stop.sh
```

---

## 工程结构

```
realtime-novel/
├── backend/             # Python 后端（FastAPI + ReAct Agent）
├── frontend/            # Vue 3 + TypeScript 前端
├── data/                # SQLite + 章节文件（gitignored）
├── scripts/             # 启动 / 停止脚本
├── tests/               # E2E 集成测试
├── docs/                # 技术文档（13 篇）
├── .spec/               # 设计规格（里程碑规划）
├── .realtime-novel/     # 工程内约束（conventions.md）
├── pyproject.toml       # Python 包配置
├── CHANGELOG.md         # 版本变更记录
└── .llm_api_key         # LLM Key（gitignored）
```

完整目录树与各文件职责见对应 docs 章节。
