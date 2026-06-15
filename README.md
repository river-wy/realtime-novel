# Realtime Novel

> **创建**：2026-06-11
> **作者**：欧尼酱 wuyu49（项目发起人）+ 蕾姆酱 🩵（协调）
> **状态**：v0.3 推进中 · 骨架搭建阶段（5 子包结构定型）

---

## 这是什么

一个**实时生成 + 可干预**的小说阅读产品。用户在读的过程中介入剧情走向，作者 / 读者权力对等。当前处于 v0.2 → v0.3 演进期，已完成 21 万字真实 LLM 评测 demo。

---

## 当前进度

```
v0.1 (mock 评测)        ✅ 完成
v0.2 (真 LLM 20 章)     ✅ 完成 · 4/5 指标达标
v0.3 (产品骨架搭建)     ⏳ 推进中
  M-α (S1+S2 数据层)    ✅ 骨架 0.1 完成
  M-β (S4 接 LLM)       ✅ 骨架 0.2 完成
  M-γ (S3 启动链路)     📍 下一步
  M-δ (S5 干预+回档)    ⏳
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
→ 工程结构 → 见本文"工程结构"小节

### 🔬 调研 / 想看评测数据
→ [`docs/eval-notes/v0.2-real-llm.md`](docs/eval-notes/v0.2-real-llm.md) · 真 LLM 20 章报告
→ [`docs/design/04-evaluation.md`](docs/design/04-evaluation.md) · 5 指标方法

### 📚 想看小说本身
→ [`projects/demo-urban-romance/chapters/`](projects/demo-urban-romance/chapters/) · 22 章生成产物（demo 20 章 + M-β 验证 2 章）

---

## 工程结构

5 子包分层（经典分层模式，参考 FastAPI / Click / pytest）：

```
realtime_novel/
├── __init__.py         # 包入口（暴露分组）
├── __main__.py         # python -m realtime_novel 入口
├── core/               # 核心数据模型（不依赖外部服务）
│   ├── exceptions.py
│   ├── world_tree.py
│   ├── project.py
│   └── schemas/        # 7 件 Schema + ChapterSummary
├── services/           # 业务服务（S1-S5 orchestrators）
│   └── chapter_generator.py
├── adapters/           # 外部依赖适配
│   ├── llm.py          # 独立 LLM 客户端（不引用 lunaris）
│   ├── prompt.py       # 三层 prompt 组装
│   ├── seed_weight.py  # 4 维权重计算
│   └── io.py           # YAML/JSON 读写
├── cli/                # argparse CLI
│   └── main.py
└── utils/              # 工具类
    ├── version.py
    └── seed_demo.py
```

完整规范：[`.realtime-novel/conventions.md`](.realtime-novel/conventions.md) · 13 条强约束

---

## 怎么跑

### 装环境（一次性）

```bash
cd /Users/wuyu/creativeToys/realtime-novel
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 跑验收

```bash
# M-α 验收（5 项，~1 分钟）
python tests/m1/test_skeleton.py

# M-β 验收（5 项 + 跑真 LLM ~60s/章）
python tests/m2/test_chapter.py
```

### CLI 用法

```bash
# 项目管理
realtime-novel load --project-id demo-urban-romance

# 生成下一章（接 LLM 客户端，跑真 LLM）
realtime-novel generate --project-id demo-urban-romance

# 回档到指定 Node（内存操作）
realtime-novel rollback --project-id demo-urban-romance --node-id node-001

# 新建项目（M-γ 阶段实装 5 步引导）
realtime-novel new --project-id my-story
```

### LLM 配置

realtime_novel **完全独立**，不引用 lunaris。

- 配置文件：`./config.private.json`（**不入仓**，含 `llm` 段：baseUrl / apiKey / default_model）
- 环境变量覆盖：`export LLM_CONFIG_PATH=/path/to/your/config.json`
- 默认模型：`deepseek-v4-pro`（OpenAI 兼容协议）

如果还没有 `config.private.json`，从 lunaris 那边拷一份 `llm` 段过来即可（`scp ~/AiTest/lunaris/config.private.json` 然后 `jq '{llm: .llm}'` 抽出）。

### 跑评测（v0.1 / v0.2）

```bash
# v0.1 评测（mock，5 分钟）
cd docs/eval-notes/code/v0.1 && python3 main.py

# v0.2 评测（真 LLM，30 分钟）
cd docs/eval-notes/code/v0.2
N_CHAPTERS=20 python3 main.py
```

---

## 版本

`0.3.0-alpha` · 详见 [`CHANGELOG.md`](CHANGELOG.md)
