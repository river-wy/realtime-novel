# 后端文档索引

> **版本**：v0.9.6 · **commit**：`e717e5b` · **最后更新**：2026-07-02

按主题分篇。每篇聚焦一个层次，可独立阅读；交叉引用已在文中标注。

## 文档列表

| 文档 | 一句话简介 |
|---|---|
| [architecture.md](./architecture.md) | 整体架构（分层 + 跨层调用链 + 启动流程），理解后端全貌的入口 |
| [agent.md](./agent.md) | 4 顶层 Agent + ReAct 引擎 + Session Cache + Onboarding + 22 工具 + 数据流 |
| [persistence.md](./persistence.md) | SQLite 存储 + 19 张表 schema + Repository 列表 + 迁移机制 + 软删除 + 回档 |
| [services.md](./services.md) | 业务编排层（6 个 service 的内部方法 + 编排模式 + 业务流示例） |
| [adapters.md](./adapters.md) | LLM 调用流 + DeepSeek / Gemini Provider + 路由 + 重试 + 流式 |
| [core.md](./core.md) | WorldTree 聚合根 + 7 件基座 Schema + EventBus + 异常层级 |
