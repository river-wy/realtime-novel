# Realtime Novel

> **创建**：2026-06-11
> **作者**：欧尼酱 wuyu49（项目发起人）+ 蕾姆酱 🩵（协调）
> **状态**：v0.3 推进中 · 骨架搭建阶段

---

## 这是什么

一个**实时生成 + 可干预**的小说阅读产品。用户在读的过程中介入剧情走向，作者 / 读者权力对等。当前处于 v0.2 → v0.3 演进期，已完成 21 万字真实 LLM 评测 demo。

---

## 当前进度

```
v0.1 (mock 评测)        ✅ 完成
v0.2 (真 LLM 20 章)     ✅ 完成 · 4/5 指标达标
v0.3 (产品骨架搭建)     ⏳ 推进中 · M-α 待启动
```

详细路线图：[`docs/roadmap/v0.3-product-skeleton.md`](docs/roadmap/v0.3-product-skeleton.md)

---

## 从哪看

按你的角色选一条路径：

### 📖 路人 / 想了解产品
→ [`docs/design/00-overview.md`](docs/design/00-overview.md) · 一份文档讲清产品是什么

### 🏗️ 工程师 / 想动手做
→ [`docs/design/01-world-tree.md`](docs/design/01-world-tree.md) · WorldTree 是产品核心数据结构
→ [`docs/design/03-schemas.md`](docs/design/03-schemas.md) · 7 件产物 Schema
→ [`docs/roadmap/v0.3-product-skeleton.md`](docs/roadmap/v0.3-product-skeleton.md) · 骨架 5 件套 S1-S5

### 🔬 调研 / 想看评测数据
→ [`docs/eval-notes/v0.2-real-llm.md`](docs/eval-notes/v0.2-real-llm.md) · 真 LLM 20 章报告
→ [`docs/design/04-evaluation.md`](docs/design/04-evaluation.md) · 5 指标方法

### 📚 想看小说本身
→ [`generated-stories/case-1-urban-romance/`](generated-stories/case-1-urban-romance/) · 20 章生成产物（21 万字）

---

## 怎么跑

```bash
# 装环境 (一次性)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 跑 M-α 验收 (骨架 0.1 · 5 项)
python verify.py

# 装载 demo 数据 (M-α 后首跑需要)
python -m realtime_novel._seed_demo
```

跑评测（v0.1 / v0.2）：

```bash
# v0.1 评测（mock，5 分钟）
cd docs/eval-notes/code/v0.1 && python3 main.py

# v0.2 评测（真 LLM，30 分钟）
cd docs/eval-notes/code/v0.2
N_CHAPTERS=20 python3 main.py
```

LLM 配置复用 `~/AiTest/lunaris/config.private.json`，无需额外配置。

---

## 工程约定

所有目录 / 命名 / commit 格式约束见：[`.realtime-novel/conventions.md`](.realtime-novel/conventions.md)

---

## 主理

- 发起：欧尼酱 wuyu49
- 协调：蕾姆酱 🩵
- 创建：2026-06-11
