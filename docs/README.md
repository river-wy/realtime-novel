# 技术文档索引

> **最后更新**：2026-07-02 · **版本**：v0.9.6 · **commit**：`e717e5b`

realtime-novel 工程的技术沉淀。新人按以下顺序读 1 小时可上手。

---

## 后端（7 篇）

按分层从外到内阅读：架构 → Agent → Service → Persistence → Adapter → Core。

| 文档 | 一句话简介 |
|---|---|
| [backend/architecture.md](./backend/architecture.md) | 整体架构（分层 + 跨层调用链 + 启动流程），理解后端全貌的入口 |
| [backend/agent.md](./backend/agent.md) | 4 顶层 Agent + ReAct 引擎 + Session Cache + Onboarding + 22 工具 |
| [backend/persistence.md](./backend/persistence.md) | SQLite 存储 + 19 张表 schema + Repository 列表 + 迁移机制 |
| [backend/services.md](./backend/services.md) | 业务编排层（6 个 service 的内部方法 + 编排模式） |
| [backend/adapters.md](./backend/adapters.md) | LLM 调用流 + DeepSeek / Gemini Provider + 路由 + 重试 |
| [backend/core.md](./backend/core.md) | WorldTree 聚合根 + 7 件基座 Schema + EventBus + 异常层级 |

## 前端（7 篇）

| 文档 | 一句话简介 |
|---|---|
| [frontend/architecture.md](./frontend/architecture.md) | 前端架构总览：技术栈、5 个路由、3 个 Pinia store、Axios / WS 概览、TypeScript |
| [frontend/api-integration.md](./frontend/api-integration.md) | HTTP API + WebSocket 集成手册：Axios 配置、12 端点 DTO、WS 7 种事件处理 |
| [frontend/state-management.md](./frontend/state-management.md) | 3 个 Pinia store + useStewardChat composable + WS 状态机 |
| [frontend/pages-and-components.md](./frontend/pages-and-components.md) | 4 个 view + ChatBox 组件 + 路由树 + 组件复用 |
| [frontend/styling.md](./frontend/styling.md) | 14 组 CSS 变量 + 3 个样式文件 + 样式约定 |
| [frontend/build-and-deploy.md](./frontend/build-and-deploy.md) | 开发 / 构建 / 部署（Nginx + FastAPI 静态）+ TypeScript 配置 |
| [frontend/api-self-check.md](./frontend/api-self-check.md) | 端点对齐自检报告：调用层 100% + 3 个 P1 + 5 个 P2 |

---

## 阅读顺序建议

**新人入职 1 小时路径**：
1. 根 [README.md](../README.md)（是什么 / 怎么跑）
2. [backend/architecture.md](./backend/architecture.md)（后端全貌，30 分钟）
3. [backend/agent.md](./backend/agent.md)（最核心 — 管家 / 文笔家 / 架构师 / Validator）
4. [frontend/architecture.md](./frontend/architecture.md)（前端全貌，20 分钟）
5. [frontend/api-integration.md](./frontend/api-integration.md)（前后端如何连）

**发起 PR 前必看**：
- [frontend/api-self-check.md](./frontend/api-self-check.md)（看你改的代码有没有触发 P1/P2）
- [backend/architecture.md §2 分层依赖规则](./backend/architecture.md)（你的 import 有没有越层）

---

## 文档维护

所有 docs 由 2026-07-02 docs 重构生成（基于 commit `e717e5b`），反映 v0.9.6 实际状态。
