# Realtime Novel · 文档入口

> **创建**：2026-06-15
> **作者**：蕾姆酱 🩵
> **状态**：定稿

---

## 这是什么

`docs/` 是项目的**推导与设计材料**——产品设计、调研、评测、路线图。任何非工程代码的产物都进这里。

工程代码在 [`realtime_novel/`](../realtime_novel/)（产品包）。生成产物随项目保存在 [`projects/{id}/chapters/`](../projects/)。评测代码在 [`docs/eval-notes/code/`](eval-notes/code/)（属于评测笔记的一部分）。

---

## 怎么读

按主题分 4 个子目录，新人按以下顺序看：

| 顺序 | 路径 | 看什么 | 谁需要看 |
|------|------|--------|---------|
| 1️⃣ | [`design/00-overview.md`](design/00-overview.md) | 产品是什么 + 原则 | 所有人 |
| 2️⃣ | [`design/01-world-tree.md`](design/01-world-tree.md) | WorldTree + 启动链路 | 工程师 / 设计师 |
| 3️⃣ | [`design/02-consistency.md`](design/02-consistency.md) | 一致性方案（4 维种子权重）| 工程师 |
| 4️⃣ | [`design/03-schemas.md`](design/03-schemas.md) | 7 件产物 Schema | 工程师 |
| 5️⃣ | [`design/04-evaluation.md`](design/04-evaluation.md) | 5 指标评测方法 | 调研者 |

| 按需 | 路径 | 看什么 |
|------|------|--------|
| 🔬 | [`eval-notes/`](eval-notes/) | 评测笔记（v0.1 / v0.2）+ 代码 |
| 🛣️ | [`roadmap/`](roadmap/) | 当前唯一路线图（v0.3 骨架）|
| 📚 | [`research/`](research/) | 立项时的调研材料 |

---

## 维护规则

- 本目录文件数 > 10 → 必分子目录（已在子目录化）
- 文档顶部必有元信息（创建 / 作者 / 状态）
- 数字编号**只在 `design/`** 下用，其他位置用日期或主题
- 路线图**唯一一份**（历史版本进 `roadmap/archive/`）

完整约束见 [`../.realtime-novel/conventions.md`](../.realtime-novel/conventions.md)
