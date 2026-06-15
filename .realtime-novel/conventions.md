# Realtime Novel · 工程框架规范

> **作用**：定义本工程所有文件 / 目录 / commit / 命名 / 版本 / 依赖 / 测试的统一规则
> **权威性**：本文件 = 工程级宪法。任何与本文件冲突的文件结构视为违规。
> **作者**：蕾姆酱 🩵
> **创建**：2026-06-15
> **版本**：v1.0（M-α/M-β 阶段 7 条 + 重构期 +6 条）

---

## 0. 关于本规范

### 0.1 演进历史

| 版本 | 时间 | 变更 |
|------|------|------|
| v1.0 | 2026-06-15 | 初版：M-α/M-β 7 条 + 重构期 6 条 = 13 条强约束 |
| (未来) | M-γ | 加测试规范（pytest / conftest / fixtures）|
| (未来) | M-δ | 加干预/回档规范 |

### 0.2 适用范围

**仅适用于本工程**。`.openclaw/workspace/AGENTS.md` 的全局规范（`outputs/notes/tmp/research/eval/` 等）**不直接适用**——本工程有独立 Git 仓库、独立目录哲学。

冲突时的优先级：
1. **本文件 > workspace 全局规范**（本工程内绝对权威）
2. **欧尼酱口头指令 > 本文件**（如有冲突，蕾姆酱会同步更新本文件）

---

## 1. 目录布局规则（13 条强约束）

### 1.1 顶层结构（白名单）

工程根目录下**只允许**以下 9 类入口：

| 目录/文件 | 角色 | 备注 |
|-----------|------|------|
| `README.md` | 项目入口 | 4 段结构：是什么 / 进度 / 从哪看 / 怎么跑 |
| `CHANGELOG.md` | 变更日志 | 每次发版 / 重构 / 重大变更必更新 |
| `pyproject.toml` | 包元信息 + 依赖 + CLI 入口 | 必含 `[project]` / `[project.scripts]` |
| `realtime_novel/` | 产品代码包 | 5 子包结构（见 §1.2）|
| `tests/` | 测试代码 | 验收脚本 + pytest 测试 |
| `docs/` | 推导与设计材料 | 任何"非工程代码"的产物都进这里 |
| `projects/` | 实际项目数据 | 装载 demo / 用户创建的项目（含 7 件 YAML + chapters/）|
| `.realtime-novel/` | 工程内规则 | 本文件所在 |
| `.gitignore` | Git 忽略规则 | 必备 |
| `.venv/` | Python 虚拟环境 | **不入仓**（gitignore 已覆盖）|
| `config.private.json` | LLM 配置（**不入仓**）| 含 llm 段（baseUrl/apiKey/model）|

**禁止在工程根目录出现**：
- ❌ 散落的 `*.md`（除 README / CHANGELOG）
- ❌ 散落的 `verify_*.py` / `test_*.py`（必须进 `tests/{m1,m2,m3}/`）
- ❌ 散落的 `__init__.py` / `main.py` / `cli.py`（必须进 `realtime_novel/` 内子包）
- ❌ `src/` 套层（产品代码直接在 `realtime_novel/`）
- ❌ `eval/` 在工程根（属于 `docs/eval-notes/code/` 的附属）

### 1.2 `realtime_novel/` 5 子包结构（**强约束**）

经典分层（参考 FastAPI / Click / pytest 业界标准）：

```
realtime_novel/
├── __init__.py        # 包入口 · 暴露分组
├── __main__.py        # python -m realtime_novel 入口
├── core/              # 核心数据模型（不依赖 services/adapters）
│   ├── __init__.py
│   ├── exceptions.py  # 异常层级
│   ├── world_tree.py
│   ├── project.py
│   └── schemas/       # 7 件 Schema + ChapterSummary
├── services/          # 业务服务（S1-S5 orchestrators）
│   ├── __init__.py
│   └── chapter_generator.py
├── adapters/          # 外部依赖适配（LLM / IO / Prompt / 算法）
│   ├── __init__.py
│   ├── llm.py         # 独立 LLM 客户端
│   ├── prompt.py
│   ├── seed_weight.py
│   └── io.py
├── cli/               # 命令行入口（argparse，零依赖）
│   ├── __init__.py
│   └── main.py
└── utils/             # 工具类
    ├── __init__.py
    ├── version.py
    └── seed_demo.py
```

**层间依赖规则**：
- `core/` 不依赖 `services/` / `adapters/` / `cli/`
- `services/` 可以依赖 `core/` + `adapters/`
- `adapters/` 可以依赖 `core/`（如 prompt.py 用 schemas）
- `cli/` 可以依赖任何层
- `utils/` 独立，无业务依赖

### 1.3 `docs/` 子目录

当文件数 > 10 时必须分子目录。**已**子目录化：

| 子目录 | 角色 |
|--------|------|
| `docs/design/` | 产品设计文档（5 份定稿）|
| `docs/research/` | 调研材料 |
| `docs/eval-notes/` | 评测笔记 + `code/` 子目录 |
| `docs/roadmap/` | 路线图（**唯一一份 active**）|

### 1.4 `tests/` 子目录

```
tests/
├── README.md          # tests 怎么写 / 怎么跑（M-γ 时实装）
├── conftest.py        # pytest 配置 + fixtures（M-γ 时实装）
├── m1/                # M-α 验收
│   └── test_skeleton.py
├── m2/                # M-β 验收
│   └── test_chapter.py
└── m3/                # M-γ 验收（待建）
    └── test_onboarding.py
```

### 1.5 文件数硬约束

| 场景 | 触发条件 | 处理 |
|------|---------|------|
| 同一目录下文件 > 10 | 任意 | 必须分子目录 |
| 单文件 > 2000 行 | 任意 | 必须拆分 |
| 多人共享目录 | 多文件 | 按人/任务建子目录 |

---

## 2. 命名规则

| 类型 | 命名风格 | 示例 |
|------|---------|------|
| 目录 | snake_case | `realtime_novel/`, `chapter_generator.py` |
| 模块 | snake_case | `chapter_generator.py` ✅ / `chapgen.py` ❌ |
| 类 | PascalCase | `ChapterGenerator` ✅ / `chapterGenerator` ❌ |
| 函数 | snake_case | `generate_next` ✅ / `generateNext` ❌ |
| 变量 | snake_case | `current_segment` ✅ / `currentSegment` ❌ |
| 常量 | UPPER_SNAKE | `SEGMENTS_PER_CHAPTER` |
| Markdown | kebab-case | `world-tree.md` ✅ / `wt.md` ❌ |
| 测试 | `test_` 前缀 | `test_skeleton.py` ✅ |

**禁止的命名**：
- ❌ 缩写为代价的"短名"（`wt.py` / `gen.py` / `llm_v2.py`）
- ❌ 前缀日期命名（`2026-06-15-xxx.md`——日期放文档元信息顶部）
- ❌ 大写驼峰目录（`WorldTree/` 混在 snake_case 目录里突兀）
- ❌ 文件名带下划线前缀（`_seed_demo.py` 私有约定——公开工具不放 `_`）
- ❌ 文件名带空格或中文

---

## 3. Commit 格式（Conventional Commits）

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

**scope 限定**：
- `feat(s1)` / `feat(s2)` / ... `feat(s5)` — 骨架 5 件套
- `feat(eval)` — 评测代码
- `feat(llm)` / `feat(prompt)` / `feat(io)` — adapters
- `feat(cli)` — CLI
- `docs(design)` / `docs(roadmap)` / `docs(eval-notes)` / `docs(readme)` — 文档分类
- `chore(structure)` — 目录结构调整
- `chore(deps)` — 依赖变更

**范本**：
```bash
git commit -m "feat(s1): 实现 ProjectManager.create() / load()"
git commit -m "docs(readme): 重写 4 段结构"
git commit -m "chore(structure): 5 子包重构 + 验收脚本进 tests/"
```

---

## 4. 版本管理（semver）

`realtime_novel/__init__.py` 的 `__version__` 遵循 [semver](https://semver.org/)：

| 阶段 | 格式 | 含义 |
|------|------|------|
| alpha | `0.x.0-alpha` | 早期开发，破坏性变更随时发生 |
| beta | `0.x.0-beta` | 功能基本完成，进入稳定性测试 |
| rc | `0.x.0-rc1` | 发布候选，只修 bug |
| stable | `1.0.0` | 正式发布，向后兼容 |

**当前阶段**：`0.3.0-alpha`（M-α/M-β 已完成，M-γ 进行中）

---

## 5. 依赖管理

### 5.1 `pyproject.toml` 优先

- **主依赖**写在 `[project] dependencies`
- **extras** 写在 `[project.optional-dependencies]`（如 `pip install realtime_novel[llm]`）
- **dev 依赖**写在 `[project.optional-dependencies.dev]`

### 5.2 当前依赖清单

```toml
[project]
dependencies = [
    "pydantic>=2.0",    # 7 件 Schema 校验 + 序列化
    "pyyaml>=6.0",      # YAML 落盘
    "certifi",          # LLM 客户端 SSL 绕开 macOS
]
```

**无第三方重型依赖**（不引 Click / pytest / loguru 之类的）——保持轻量。

### 5.3 LLM 配置（完全独立）

- 配置路径：`./config.private.json`（**不入仓**）
- 环境变量覆盖：`LLM_CONFIG_PATH=/path/to/config.json`
- 默认模型：`deepseek-v4-pro`（OpenAI 兼容协议）
- **不引用 lunaris 任何代码**（2026-06-15 欧尼酱定调）

---

## 6. 文档规范

### 6.1 顶部三行（强制）

每个 `.md` 文档**必须**有顶部元信息（除 README）：

```markdown
# {标题}

> **创建**：YYYY-MM-DD
> **作者**：{欧尼酱 wuyu49 / 蕾姆酱 🩵 / 其他}
> **状态**：{草稿 / 对齐中 / 定稿 / 已废弃}
```

### 6.2 章节定位（强制）

文档开头必须有 **0. 文档定位** 章节。

### 6.3 章节编号规则

- 一级章节用 0/1/2/3（0 通常是"文档定位"）
- 二级用 1.1 / 1.2
- 最多到三级
- 章节标题 ≤ 20 字

---

## 7. 测试规范（**M-γ 时建**）

**当前 M-α/M-β 阶段**：
- 验收脚本放 `tests/mN/test_*.py`（已落地）
- 直接 `python tests/mN/test_*.py` 跑

**M-γ 时升级为 pytest 风格**：
- 加 `tests/conftest.py` 公共 fixtures
- 加 `pyproject.toml` 配置 `[tool.pytest.ini_options]`
- 验收脚本改用 pytest assertion
- `pytest tests/m1/ -v` 跑

---

## 8. CLI 规范

### 8.1 用 argparse 不用 Click/Typer

- **零依赖**（Click 加 1 个重型包不必要）
- 4 个子命令：`new` / `load` / `generate` / `rollback`
- 入口：`python -m realtime_novel <subcommand> [args]`
- 每个子命令独立函数（`cmd_*.py` 或 `cli/main.py` 内部分组）

### 8.2 CLI 不跑验收

- `tests/` 是 pytest 自动化，CLI 只做产品功能
- 不重叠（详见路线图 §4 M-α 决策）

### 8.3 错误处理

- 异常 → 友好错误信息 + exit 1
- 不在 CLI 里塞 `try/except` 兜底（异常透传到 main，让 traceback 暴露）

---

## 9. 强约束清单（违反视为违规）

| # | 规则 |
|---|------|
| 1 | 根目录不散落 `.md`（除 README / CHANGELOG）|
| 2 | 散落验收脚本必进 `tests/mN/` |
| 3 | 产品代码在 `realtime_novel/` 内 5 子包，**不用 `src/`** |
| 4 | 7 件 Schema 只在 `core/schemas/` |
| 5 | adapters 只依赖 core（不依赖 services）|
| 6 | LLM 客户端不引用 lunaris 任何代码 |
| 7 | 文件名 = 内容，不缩写 |
| 8 | 文档顶部必有元信息 |
| 9 | commit 用 Conventional Commits |
| 10 | 单文件 ≤ 2000 行 |
| 11 | 路线图唯一（`docs/roadmap/vX.Y-*.md` 只能 1 份 active）|
| 12 | 数字编号只在 `docs/design/` 下用 |
| 13 | `*.private.json` 不入仓 |
| 14 | **生成产物随项目保存**（在 `projects/{id}/chapters/`，**不**单独建 `generated-stories/`）|

---

## 10. 演进记录

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-06-15 | 初版：M-α/M-β 7 条 + 重构期 6 条 = 13 条强约束 | 蕾姆酱 🩵 |
