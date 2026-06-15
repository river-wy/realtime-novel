# Realtime Novel · 工程内约束

> **作用**：定义本工程所有文件 / 目录 / commit / 命名的统一规则。后续所有产出物必须遵循。
> **权威性**：本文件 = 工程级宪法。任何与本文件冲突的文件结构视为违规。
> **作者**：蕾姆酱 🩵
> **创建**：2026-06-15
> **对应演进**：源于 v0.2 收口后结构混乱复盘，2026-06-15 12:08 欧尼酱对齐

---

## 1. 目录布局规则

### 1.1 顶层结构（白名单）

工程根目录下**只允许**以下 7 类入口：

| 目录/文件 | 角色 | 备注 |
|-----------|------|------|
| `README.md` | 项目入口 | 4 段结构：是什么 / 进度 / 从哪看 / 怎么跑 |
| `docs/` | 推导与设计材料 | 任何"非工程代码"的产物都进这里 |
| `realtime_novel/` | 产品代码包 | 根目录直接展开，**不**用 `src/` 套层 |
| `generated-stories/` | 生成产物 | 章节文本，按 case 分目录 |
| `.realtime-novel/` | 工程内规则 | 本文件所在 |
| `.gitignore` | Git 忽略规则 | 必备 |
| `LICENSE` | 许可证 | 暂未添加，按需 |

**禁止在工程根目录出现**：
- ❌ 散落的 `*.md`（除 README）
- ❌ `tests/` / `scripts/` / `outputs/` / `notes/` / `tmp/` / `research/` / `eval/`（workspace 习惯**不**适用于本工程）
- ❌ `src/` 套层（产品代码直接放根）

### 1.2 `docs/` 子目录

docs 是**唯一允许子目录嵌套**的位置。当文件数 > 10 时必须分子目录。

| 子目录 | 角色 | 命名 |
|--------|------|------|
| `docs/design/` | 产品设计文档 | 5 份定稿（`00-overview` ~ `04-evaluation`） |
| `docs/research/` | 调研材料 | 日期或主题命名 |
| `docs/eval-notes/` | 评测笔记 | `vX.Y-xxx.md` 形式 |
| `docs/eval-notes/code/` | 评测代码 | `v0.1/` / `v0.2/` 子目录 |
| `docs/roadmap/` | 路线图 | `vX.Y-主题.md` 形式 |

**禁止在 docs/ 根目录出现**：
- ❌ 任何散落 `.md`（除 `docs/README.md`）
- ❌ 散落的 `01-` `02-` 编号（编号只在 `design/` 下用）

### 1.3 文件数硬约束

| 场景 | 触发条件 | 处理 |
|------|---------|------|
| 同一目录下文件 > 10 | 任意 | 必须分子目录 |
| 单文件 > 2000 行 | 任意 | 必须拆分 |
| 多人共享目录 | 多文件 | 按人/任务建子目录 |

---

## 2. 文档编号规则

### 2.1 只在 `docs/design/` 下用数字编号

```
docs/design/00-overview.md         # 产品定位
docs/design/01-world-tree.md       # 启动链路 + WorldTree
docs/design/02-consistency.md      # 一致性方案
docs/design/03-schemas.md          # 7 件产物 Schema
docs/design/04-evaluation.md       # 评测方法
```

编号 = 主题，**不是**创建时间。后续新增 design 文档接 05+。

### 2.2 其他位置禁止数字编号

- ❌ `docs/eval-notes/01-...` → 改为 `v0.1-...`
- ❌ `docs/roadmap/01-...` → 改为 `v0.3-...`
- ❌ `docs/research/01-...` → 改为日期或主题

### 2.3 路线图单一原则

**任何时刻只允许有一份 active 路线图**，命名 `docs/roadmap/vX.Y-{主题}.md`。

历史路线图要保留？→ 加 `archive/` 子目录，但**不在默认阅读路径里**。

---

## 3. 命名规则

### 3.1 文件名 = 内容

| 类型 | 命名风格 | 示例 |
|------|---------|------|
| Markdown | kebab-case | `world-tree.md` ✅ / `wt.md` ❌ |
| Python 模块 | snake_case | `chapter_generator.py` ✅ / `chapgen.py` ❌ |
| Python 包目录 | snake_case | `realtime_novel/` ✅ / `rn/` ❌ |
| YAML/JSON | snake_case | `main_plot.yaml` ✅ / `mp.yaml` ❌ |
| 测试 | `test_` 前缀 | `test_world_tree.py` ✅ |

### 3.2 禁止的命名

- ❌ 缩写为代价的"短名"（`wt.py` / `gen.py` / `eval_v1.py`）
- ❌ 前缀日期命名（`2026-06-15-xxx.md`——日期放文档元信息顶部）
- ❌ 大写驼峰（`WorldTree.md`——混在 kebab-case 目录里突兀）
- ❌ 文件名带空格或中文（除顶层 README 外）

---

## 4. Commit 格式

### 4.1 Conventional Commits 前缀

```
<type>(<scope>): <subject>
```

| type | 含义 | 何时用 |
|------|------|--------|
| `feat` | 新功能 | 加模块 / 加产品代码 / 加 API |
| `fix` | 修 bug | 修产品 bug / 修评测 bug |
| `docs` | 文档变更 | 写/改 docs/ 下文件 |
| `refactor` | 重构 | 改产品代码结构但不改行为 |
| `test` | 测试 | 加测试 / 改测试 |
| `chore` | 杂项 | 改 .gitignore / 改 dependencies / 改工具 |

### 4.2 scope 限定

- `feat(s1)` / `feat(s2)` / ... `feat(s5)` — 骨架 5 件套
- `feat(eval)` — 评测代码
- `docs(design)` / `docs(roadmap)` / `docs(eval-notes)` / `docs(readme)` — 文档分类
- `chore(structure)` — 目录结构调整

### 4.3 范本

```bash
git commit -m "feat(s1): 实现 ProjectManager.create() / load()"
git commit -m "docs(readme): 重写 4 段结构"
git commit -m "chore(structure): docs 收口 + eval-notes/code 收编"
```

---

## 5. 文档强制元信息

### 5.1 顶部三行（强制）

每个 `.md` 文档**必须**有顶部元信息：

```markdown
# {标题}

> **创建**：YYYY-MM-DD
> **作者**：{欧尼酱 wuyu49 / 蕾姆酱 🩵 / 其他}
> **状态**：{草稿 / 对齐中 / 定稿 / 已废弃}
```

### 5.2 章节定位（强制）

文档开头必须有 **0. 文档定位** 章节，写明：
- 本文档回答什么问题
- 与其他文档的关系（关联 / 派生 / 替代）
- 范围（什么在 / 什么不在）

### 5.3 章节编号规则

- 一级章节用 0/1/2/3（0 通常是"文档定位"）
- 二级用 1.1 / 1.2
- 最多到三级（避免无限嵌套）
- 章节标题 ≤ 20 字

---

## 6. 强约束（违反视为违规）

| # | 规则 | 违反示例 |
|---|------|---------|
| 1 | 根目录不散落 `.md` | `workspace/test.md` ❌ |
| 2 | docs 超过 10 文件必分 | `docs/` 下 20 个 `.md` 打平 ❌ |
| 3 | 路线图唯一 | `docs/05-xxx.md` + `docs/06-xxx.md` 同时存在 ❌ |
| 4 | 编号只在 design/ 下用 | `docs/research/01-foo.md` ❌ |
| 5 | 文件名 = 内容，不缩写 | `wt.md` / `gen.py` ❌ |
| 6 | 文档顶部必有元信息 | 无 `> 创建/作者/状态` 的 `.md` ❌ |
| 7 | commit 用 Conventional Commits | `git commit -m "改了点东西"` ❌ |
| 8 | 单文件 ≤ 2000 行 | 超长文件 ❌（必须拆分） |
| 9 | 产品代码在根目录 | `src/realtime_novel/` ❌（工程不用 src） |
| 10 | eval/ 不在工程根 | `eval/` 在工程根目录 ❌（应挪到 `docs/eval-notes/code/`） |

---

## 7. 演进记录

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-06-15 | 初版：v0.2 收口后结构混乱复盘，定义 7 条强约束 | 蕾姆酱 🩵 |

---

## 附录：与 workspace 全局规范的关系

`~/.openclaw/workspace/AGENTS.md` 的"工作区写入规范"（`outputs/` / `notes/` / `tmp/` / `research/` 等）**不直接适用于本工程**——本工程是独立 Git 仓库，有自己的目录哲学。

冲突时的优先级：
1. **本文件 > workspace 全局规范**（本工程内绝对权威）
2. **欧尼酱口头指令 > 本文件**（如有冲突，蕾姆酱会同步更新本文件）
