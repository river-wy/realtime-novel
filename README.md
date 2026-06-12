# realtime-novel · 实时小说项目

> 一个由欧尼酱发起、长期打磨中的项目。
> **当前状态：v0.2 真实长程评测通过（4/5 指标达标），已生成 21 万字 demo。**
> 创建：2026-06-11 | 主线推进：2026-06-12 | 主理：蕾姆酱 🩵

---

## 项目一句话

让用户通过「**实时生成** + **可干预** + **双视角切换**」的方式阅读和推进小说，解决传统小说「套路化 + 缺沉浸感」的痛点。

---

## 当前阶段：v0.2 完成

| 维度 | 状态 |
|------|------|
| 产品定位 | ✅ v3.1 沉浸感模型收口 |
| 启动流程 | ✅ 5 步链路 + 7 件产物（6→7 件升级）|
| 一致性方案 | ✅ 4 维种子权重 + 三层 prompt + 阶段摘要 |
| 数据 Schema | ✅ 7 件产物 YAML 化（03） |
| 评测方法 | ✅ 5 核心指标 + 4 阶段 pipeline |
| 真实 LLM 验证 | ✅ v0.2 跑 20 章真 LLM，**4/5 指标达标** |

**唯一未达标的指标**：overdue 触发命中率（0/0 overdue）—— 20 章没触发任何种子 overdue，planned_interval 偏长。**v0.3 要调。**

---

## 目录结构

```
realtime-novel/
├── docs/                              6 份产品设计文档 (2684 行)
│   ├── 00-overview.md                 沉浸感模型 v3.1
│   ├── 01-world-contract.md           启动链路 + 7 件产物
│   ├── 02-consistency.md              一致性方案 + 4 维种子权重
│   ├── 03-product-schemas.md          7 件产物 Schema (YAML)
│   ├── 04-evaluation.md               评测方法 + 5 指标
│   └── 05-roadmap-v03.md              路线图 v0.3+
│
├── eval/                              评测代码
│   ├── v0.1/                          Mock 评测（验证机制）
│   └── v0.2/                          真 LLM 评测（20 章 + 4/5 指标达标）
│
├── generated-stories/                 ⭐ 生成的小说（21 万字 demo）
│   └── case-1-urban-romance/          都市情感题材
│       ├── chapter-01.txt             10914 字
│       ├── ...
│       └── chapter-20.txt             13357 字
│
└── research/                          06-11 立项时的测评切片
```

---

## 阅读顺序建议

1. **看 demo**：`generated-stories/case-1-urban-romance/chapter-01.txt` 起读
2. **理解设计**：`docs/00-overview.md` → `01` → `02` → `03` → `04`
3. **看评测**：`eval/v0.2/README.md` + `output/case-1-urban-romance/report.txt`

---

## 评测结果（v0.2 真 LLM · 20 章）

```
总览: 4/5 指标达标
耗时: 1902s (32 min)

✅ 种子回收率          1.0   (3/3 种子全回收)
✅ 基座约束遵守率       1.0   (无违反)
✅ 具体性颗粒密度       1.62  / 千字 (≤ 3.0 目标)
❌ overdue 触发命中率   0.0   (0/0 overdue)  ← 待调优
✅ importance 优先采纳率 1.0   (2/2 主线种子被强化)
```

---

## 下一步（v0.3 路线图）

- **M1 · v0.3 真实长程调优**：缩 planned_interval，让 20 章能触发 overdue
- **M2 · 算法调优**：基于 M1 数据调 sigmoid k 值
- **M3 · 远期架构**：300+ 章挑战（动态阶段摘要 + 向量检索）
- **M4 · 用户 UI + 多 agent**：启动链路 5 步的 UI 设计

详见 `docs/05-roadmap-v03.md`。

---

## 工作节奏约定

- **不抢跑**：方案没对齐不写代码
- **不膨胀**：核心文件只写稳定结论
- **可回滚**：所有方案默认是"暂定"

---

## 怎么自己跑评测

```bash
# 1. 配置 LLM (复用 lunaris 工程的 config.private.json)
#    lunaris 工程在 ~/AiTest/lunaris/ 下（含 config.private.json 的 llm 段）
#    如果路径不同，export LUNARIS_ROOT=/your/lunaris/path

# 2. 跑 v0.1 (mock, 5 分钟)
cd eval/v0.1 && python3 main.py

# 3. 跑 v0.2 (真 LLM, 30 分钟)
cd eval/v0.2
N_CHAPTERS=20 python3 main.py   # 20 章，约 30 min
N_CHAPTERS=80 python3 main.py   # 80 章，约 2 小时
```

输出会写到 `output/case-1-urban-romance/`，包含 `report.txt` + `metrics.json` + `chapters/`。

---

**接续方式**：每个 session 启动时读 `docs/00-overview.md` → 读 `01-04` → 看 `05-roadmap-v03.md` 决定下一步。
