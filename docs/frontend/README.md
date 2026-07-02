# 前端技术文档索引

> **版本**：v0.9.6  |  **commit**: e717e5b  |  **最后更新**：2026-07-02

realtime-novel 前端（`frontend/`）的入口索引。新人按顺序读这 4 篇就能上手。

---

## 文档列表

| 文档 | 一句话简介 |
|---|---|
| [`architecture.md`](./architecture.md) | 前端架构总览：技术栈、工程结构、5 个路由、3 个 Pinia store、Axios / WS 概览、构建部署（Nginx + FastAPI 静态）、TypeScript 路径别名 |
| [`api-integration.md`](./api-integration.md) | HTTP API + WebSocket 集成手册：Axios 配置、12 端点 DTO 表、死代码清单、管家对话 WS 7 种事件处理逻辑与连接生命周期 |
| [`api-self-check.md`](./api-self-check.md) | 端点对齐自检报告：调用层 100% 对齐 + 3 个 P1 字段契约问题 + 5 个 P2 死代码/风格建议（由另一位 Agent 于 2026-07-02 编写） |
| `overview.md` | **⚠️ 废弃** — v0.5 时期文档，仅供考古；当前请读 `architecture.md`（v0.9.6 重写版） |

---

## 阅读顺序建议

1. **新接手前端** → 先读 `architecture.md`（30 分钟过一遍）
2. **要改 HTTP 集成** → 跳到 `api-integration.md` 第 2 节（端点表 + DTO）
3. **要改管家对话 / WS** → 读 `api-integration.md` 第 3 节（事件处理逻辑）
4. **发起 PR 前** → 翻一遍 `api-self-check.md` 看你改的代码有没有触发 P1/P2

---

## 版本说明

- `architecture.md` / `api-integration.md` / 本 README 由 Agent A 于 2026-07-02 重写（commit e717e5b）
- `api-self-check.md` 由 Agent B 于同一天编写，作为对齐自检参考资料
- `overview.md` 保留 v0.5 时期的快照，**不再维护**，与新文档如有冲突以新文档为准
