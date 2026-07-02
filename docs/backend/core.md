# 后端领域核心层文档

> **更新日期**：2026-07-02
> **版本**：v0.9.6
> **Commit**：e717e5b
> **代码定位**：`backend/core/`

---

## 目录

1. [领域核心层定位](#1-领域核心层定位)
2. [WorldTree 聚合根](#2-worldtree-聚合根)
3. [7 件基座 Schema](#3-7-件基座-schema)
4. [EventBus（事件总线）](#4-eventbus事件总线)
5. [异常层级](#5-异常层级)

---

## 1. 领域核心层定位

`backend/core/` 是**领域核心层**，定位是**零外部依赖、任何层可 import**。

### 1.1 依赖规则

```
core  ← persistence（DB Row Model 继承 core.exceptions）
core  ← services（consistency_checker / cover_image_generator 调 core）
core  ← adapters（types 不依赖 core，core 不依赖 adapters）
core  ← agent（agent 调 core 的 EventBus / Schemas）
core  ← api
```

**核心约束**：
- ❌ `core` 不 import `persistence` / `services` / `adapters` / `agent` / `api`
- ❌ `core` 不调 LLM
- ❌ `core` 不直接访问 `Path("data/...")` 之类的物理路径
- ✅ `core` 只 import 标准库 + pydantic + 同目录模块

### 1.2 模块结构

```
core/
├── __init__.py
├── world_tree.py              # WorldTree 聚合根（dataclass）
├── event_bus.py               # 轻量异步 EventBus
├── exceptions.py              # 异常层级（RealtimeNovelError + 6 子类）
└── schemas/
    ├── __init__.py
    ├── world_tree.py          # 基座 #1 WorldTreeSchema
    ├── style_charter.py       # 基座 #2 StyleCharterSchema
    ├── genre_resonance.py     # 基座 #3 GenreResonanceSchema
    ├── main_plot.py           # 基座 #4 MainPlotSchema
    ├── sub_plot.py            # 基座 #6 SubPlotSchema
    ├── character_card.py      # 基座 #5 CharacterCardSchema
    ├── seed_table.py          # 基座 #7 SeedTableSchema
    └── chapter.py             # 章节摘要（ChapterSummarySchema，非基座）
```

### 1.3 设计意图

- **稳定**：core 的变化频率远低于 services/agent — 是产品的「最小公倍数」
- **可测**：所有 Pydantic Schema 都 `model_config = ConfigDict(extra="ignore")`（除 `Geography` / `CoreRule` 是 `forbid`），向后兼容旧字段
- **可移植**：未来换 FastAPI → Flask、或换 LLM Provider，core 完全不动

---

## 2. WorldTree 聚合根

`backend/core/world_tree.py`

### 2.1 定位

**S2 · WorldTree 内存模型**。在内存中聚合 7 件 Schema，提供 `to_dict / from_dict` 序列化。v0.4.1 起数据从 DB 加载（不走文件），v0.7 起删 `branches` 树形操作（`add_node / rollback_to`），v0.9（v007）后 `from_project_dir / to_project_dir` 也不存在。

### 2.2 类签名

```python
# world_tree.py:13
@dataclass
class WorldTree:
    """内存中聚合 7 件 Schema
    7 件为可选项（缺件时为 None），允许部分加载
    """
    world_tree: WorldTreeSchema
    genre_resonance: GenreResonanceSchema
    main_plot: MainPlotSchema
    character_card: CharacterCardSchema
    sub_plot: SubPlotSchema
    seed_table: SeedTableSchema
    style_pack_id: Optional[str] = None
```

> 注：v0.9.6 当前实现里 `style_pack_id` 字段仍在，但 `StyleCharter` 已不在构造参数中（7 件 = 上面 6 件 + `world_tree`，共 6 个具体 Schema）。`style_charter` 单独成件 — 后续可能重构进 `style_pack_id` 或独立字段。

### 2.3 关键方法

#### `to_dict() -> dict`

`world_tree.py:25` — 序列化为 dict-of-dicts（`mode='json'` 让 enum 序列化为字符串）：

```python
{
    "world_tree": {...},
    "style_pack_id": "...",
    "genre_resonance": {...},
    "main_plot": {...},
    "character_card": {...},
    "sub_plot": {...},
    "seed_table": {...},
}
```

#### `from_dict(data) -> WorldTree`

`world_tree.py:37` — 从 dict-of-dicts 反序列化（用 `Pydantic.model_validate`）。

#### `summary() -> Dict[str, int]`

`world_tree.py:55` — 返回各 Schema 的关键统计：

```python
{
    "main_plot_beats": int,
    "main_plot_current_beat": int,
    "character_card_characters": int,
    "character_card_relationships": int,
    "sub_plot_threads": int,
    "seed_table_seeds": int,
}
```

### 2.4 v007 删除的方法

`world_tree.py:51` 注释明确：
- ❌ `add_node / list_nodes / find_node / rollback_to`（branches_json DB 列已删，ReAct 架构下无持久化）
- ❌ `from_project_dir / to_project_dir`（v0.3 落盘式序列化，v0.4.1 入库后已不适用）

**替代路径**：
- DB 读：`ProjectRepository.load_all_artifacts(project_id) -> Dict[str, Any]`（`project_repository.py:548`）
- DB 写：9 个 Repository 各自的 `add_* / update_*` 方法

### 2.5 调用位置

- **DB 加载**（`project_repository.py:548`）返 dict 形式的 artifacts — 当前**不**经 `WorldTree` 类
- 上下文组装：`backend/agent/context_builder.py`（如有）— 视实现而定
- 主要用途：在 agent 间传递完整世界树快照

---

## 3. 7 件基座 Schema

`backend/core/schemas/`

7 件基座对应 7 个 Pydantic Schema，**全部 `extra="ignore"`** 兼容历史字段。文件名约定见各 docstring 注释。

### 3.1 WorldTreeSchema（基座 #1）

`backend/core/schemas/world_tree.py`

**文件约定**：`01-world-tree.yaml`

**字段**：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `schema_version` | str | `"1.0"` | Schema 版本 |
| `base` | dict | `{}` | `{timeline, geography, core_rules}`（暂用 dict 兜底） |
| `metadata` | dict | `{}` | 元信息 |

**嵌套 Enum**：

| Enum | 取值 | 用途 |
|------|------|------|
| `Era` | `MODERN / ANCIENT / FUTURE / FANTASY` | 时代（对应中文值） |
| `Enforcement` | `hard / soft` | 硬约束 / 软约束 |
| `AppliesTo` | `all / main / sub` | 约束作用范围 |
| `NodeType` | `main / sub / scene` | 节点类型 |
| `NodeStatus` | `pending / active / completed / abandoned` | 节点状态 |

**嵌套 Model**（虽未在主 Schema 字段中暴露，但作为 v0.3 历史基座保留）：
- `Timeline(era: Era, anchor_event: Optional[str])` — `extra="ignore"`
- `Geography(primary: str, secondary: List[str], spatial_rules: Optional[List[str]])` — `extra="forbid"`
- `CoreRule(id, statement, enforcement, applies_to)` — `extra="forbid"`
- `TreeNode(id, type, title, parent_id, status, children, beats)` — `extra="ignore"`

**v007 变更**：
- ❌ 删除 `branches` 字段（`branches_json` DB 列已删）
- v0.4.1 后：实际数据存 `world_tree` 表（5 字段最终态），此 Schema 仅作为内存模型和序列化载体

**用途**：故事地基（时间线 + 地理 + 核心规则 + 主线/支线节点树）

### 3.2 StyleCharterSchema（基座 #2）

`backend/core/schemas/style_charter.py`

**文件约定**：`02-style-charter.yaml`

**字段**：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `schema_version` | str | `"1.0"` | |
| `prose_style` | dict | `{}` | 散文式 / 对话驱动 / 意识流 / 传统小说 |
| `tone` | dict | `{}` | 基调 |
| `density` | dict | `{}` | 信息密度 |
| `taboos` | List[dict] | `[]` | 禁忌列表（forbidden / discouraged） |
| `limits` | dict | `{}` | 字数 / 节奏限制 |
| `metadata` | dict | `{}` | |

**嵌套 Enum**（备用）：
- `ProseStyle`：`PROSE / DIALOGUE / STREAM / TRADITIONAL`
- `SentenceLength`：`SHORT / MIXED / LONG`
- `TabooSeverity`：`FORBIDDEN / DISCOURAGED`

**用途**：写作的 4 维原则 + 硬约束

### 3.3 GenreResonanceSchema（基座 #3）

`backend/core/schemas/genre_resonance.py`

**文件约定**：`03-genre-resonance.yaml`

**字段**：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `schema_version` | str | `"1.0"` | |
| `accept` | List[dict] | `[]` | 用户接受什么（题材/桥段/角色类型） |
| `reject` | List[dict] | `[]` | 用户拒绝什么 |
| `anchors` | List[dict] | `[]` | 锚定元素（参考作品） |
| `metadata` | dict | `{}` | |

**嵌套 Enum**：
- `Sentiment`：`positive / negative`
- `Binding`：`hard / soft`
- `Source`：`step-1a / step-1b / user-input`

**用途**：用户接受什么 + 拒绝什么（题材共鸣维度）

**v003 变更**：信息并入 `world_tree.genre_tags_json`（实际存储），此 Schema 仍是序列化载体。

### 3.4 MainPlotSchema（基座 #4）

`backend/core/schemas/main_plot.py`

**文件约定**：`04-main-plot.yaml`

**字段**：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `schema_version` | str | `"1.0"` | |
| `beats` | List[dict] | `[]` | 节拍列表（每个 dict 含 id/title/status/trigger） |
| `current_beat` | int | `0` | 当前节拍索引 |
| `arc_phrase` | str | `""` | 整条主线一句话概括 |
| `metadata` | dict | `{}` | |

**嵌套 Enum**：
- `TriggerType`：`user-decision / auto / seed-driven`
- `BeatStatus`：`pending / active / completed`

**用途**：主线的节拍推进

**v003 变更**：实际存储改为 `main_plot` 表（1:n 节点），每行 = 一个 beat

### 3.5 CharacterCardSchema（基座 #5）

`backend/core/schemas/character_card.py`

**文件约定**：`06-character-card.yaml`

**字段**：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `schema_version` | str | `"1.0"` | |
| `characters` | List[dict] | `[]` | 角色列表（name/role/traits/speech_style/background） |
| `relationships` | List[dict] | `[]` | 关系列表（char_a/char_b/rel_type/description） |
| `metadata` | dict | `{}` | |

**用途**：角色 + 关系 + 弧光

**v003 变更**：实际存储拆为 `characters` + `character_relationships` 两张表，删 `arc / internal_state / metadata_json` 字段

### 3.6 SubPlotSchema（基座 #6）

`backend/core/schemas/sub_plot.py`

**文件约定**：`05-sub-plot.yaml`

**字段**：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `schema_version` | str | `"1.0"` | |
| `threads` | List[dict] | `[]` | 支线列表（id/title/chapter_start/chapter_end/status/priority） |
| `metadata` | dict | `{}` | |

**用途**：支线故事的容器（可挂主线，可独立）

**v003 变更**：实际存储改为 `sub_plot` 表（1:n），删 `parent_beat_id / metadata_json / linked_seeds_json / linked_chars_json`

### 3.7 SeedTableSchema（基座 #7）

`backend/core/schemas/seed_table.py`

**文件约定**：`07-seed-table.yaml`

**字段**：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `schema_version` | str | `"1.0"` | |
| `seeds` | List[dict] | `[]` | 伏笔列表（name/content/trigger/payoff/category/scope/estimated_plant/payoff/weight/status） |
| `metadata` | dict | `{}` | |

**用途**：跨章复现的颗粒，按 4 维权重排序注入 prompt

**v003 变更**：实际存储改为 `seeds` 单表（定义 + 运行时状态合并），删 `importance_primary / size / orientation / planned_interval / linked_subplot_id` 字段

### 3.8 ChapterSummarySchema（章节级，非基座）

`backend/core/schemas/chapter.py`

**字段**：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `chapter_id` | int | (必填) | 章节号 |
| `range` | str | `""` | 章节范围描述 |
| `key_events` | List[str] | `[]` | 关键事件 |
| `seed_changes` | SeedChanges | `SeedChanges()` | 种子状态变化（planted / resonating / harvested） |
| `character_state` | Dict[str, str] | `{}` | 人物状态（动态） |
| `unresolved` | List[str] | `[]` | 未解决的悬念 |

**嵌套 Model**：`SeedChanges(planted: List[int], resonating: List[int], harvested: List[int])`

**用途**：从 `real_llm.extract_summary` 抽出的章节摘要 Schema（`02-consistency.md §4.3`）

---

## 4. EventBus（事件总线）

`backend/core/event_bus.py`

### 4.1 设计原则

- 零第三方依赖，纯 asyncio
- handler 全部异步，`emit` 后立即返回（fire-and-forget）
- 保存 task 引用，防止被 GC 提前回收（官方文档警告）
- handler 异常不影响调用方，统一打 ERROR 日志

### 4.2 关键方法

#### `on(event) -> decorator`

`event_bus.py:33` — 装饰器注册：

```python
@event_bus.on("onboarding.step4_confirmed")
async def my_handler(project_id: str, **kwargs):
    ...
```

#### `register(event, handler)`

`event_bus.py:48` — 编程式注册（非装饰器场景）。

#### `emit(event, **kwargs) -> None`

`event_bus.py:56` — 触发事件，**为每个 handler 创建独立后台 Task**：

```python
for handler in handlers:
    task = asyncio.create_task(self._safe_run(event, handler, **kwargs))
    self._running_tasks.add(task)
    task.add_done_callback(self._running_tasks.discard)  # 自动清理
```

立即返回，handler 在后台并发运行。

#### `_safe_run(event, handler, **kwargs)`

`event_bus.py:74` — 包裹 handler 执行，捕获异常并打 ERROR 日志，不向上抛。

#### `handler_count(event) -> int`

`event_bus.py:84` — 返回指定事件的 handler 数量（测试用）。

### 4.3 全局单例

```python
# event_bus.py:88
event_bus = EventBus()
```

### 4.4 Onboarding Hooks 用法

`backend/agent/onboarding_hooks.py` 订阅 `onboarding.step4_confirmed` 事件：

```python
# onboarding_artifacts.py:38
await event_bus.emit("onboarding.step4_confirmed", project_id=project_id)
```

触发后并发执行（来自 `onboarding_hooks.py`）：
1. **生成项目名**（调 LLM）→ `OnboardingFlow.update_project_name_in_state`
2. **生成封面图** → `CoverImageGenerator.generate_and_save_cover` → `ProjectRepository.update_cover_image_url`
3. **推 WS 事件** `cover_image_updated` 给前端

### 4.5 事件清单

| 事件 | 触发位置 | 订阅者 |
|------|---------|--------|
| `onboarding.step4_confirmed` | `OnboardingArtifacts.mark_wtm_baseline_ready`（`onboarding_artifacts.py:38`） | `OnboardingHooks.handle_step4_confirmed`（生成项目名 + 封面图） |

未来可扩展：`chapter.generated` / `seed.planted` / `volume.completed` 等

### 4.6 注意事项

- **fire-and-forget**：emit 不等 handler 完成，调用方不能依赖 handler 执行结果
- **task 引用**：`_running_tasks: Set[asyncio.Task]` 保存 task 引用，done_callback 自动清理
- **跨事件循环**：`mark_wtm_baseline_ready`（`onboarding_artifacts.py:36`）中有 `asyncio.get_event_loop()` + `loop.create_task` 兼容代码（因为它是同步函数被同步调用场景）

---

## 5. 异常层级

`backend/core/exceptions.py`

### 5.1 层级图

```
RealtimeNovelError                    # 所有产品异常的基类
├── ConfigError                       # 配置缺失/错误
├── ProjectError                      # 项目相关错误
│   ├── ProjectNotFoundError          # 项目不存在
│   ├── ProjectAlreadyExistsError     # 项目已存在（create 时冲突）
│   └── ProjectCorruptError           # 项目 7 件不全 / 解析失败
├── LLMError                          # LLM 调用相关
│   └── LLMEmptyResponseError         # LLM 返空 content
└── GenerationError                   # 章节生成失败
    └── GenerationQualityError        # 字数不达标 / 内容质量不达标
```

### 5.2 各异常抛出时机

| 异常 | 抛出场景 | 当前抛出方 |
|------|---------|----------|
| `RealtimeNovelError` | 基类，**用户捕获时可以一把抓**所有产品异常 | — |
| `ConfigError` | `.llm_api_key` 文件找不到 / `agents.json` 解析失败 / 必填配置缺失 | `config_loader.py` |
| `ProjectNotFoundError` | `ProjectManager.load(project_id)` 找不到 | `project_manager.py` 抛 `FileNotFoundError`（**当前实现混用**，未来可改抛 `ProjectNotFoundError`） |
| `ProjectAlreadyExistsError` | `create` 时 project_id 冲突 | （v0.9.6 暂无显式抛出，由 SQLite UNIQUE 约束兜底） |
| `ProjectCorruptError` | 7 件基座缺一 / 解析失败（WorldTree `from_dict` 失败） | `core/world_tree.py` 间接抛 pydantic 校验错 |
| `LLMError` | LLM 调用相关错误的基类 | — |
| `LLMEmptyResponseError` | LLM 返 `content=""` 且 `tool_calls=None`（常见：thinking 模式 max_tokens 截断） | `agents/novel_writer.py` 等 |
| `GenerationError` | 章节生成失败的基类 | — |
| `GenerationQualityError` | 字数 < 2000 或 > 4000 / ConsistencyChecker 硬约束命中 | `agents/novel_writer.py`（content validator 阶段） |

### 5.3 当前 v0.9.6 实际状态

- 异常类**已定义**（`exceptions.py:1-49`），但**大部分业务代码尚未切换到这些类**
- 实际抛出的还是原生 Python 异常：
  - `ProjectManager.update_exploration_level`（`project_manager.py:65`）→ `FileNotFoundError`
  - `ProjectManager.rollback / delete`（`project_manager.py:217,255`）→ `ValueError`
  - `ProjectRepository.update_exploration_level`（`project_repository.py:121`）→ `ValueError`
  - `OnboardingRepository.upsert_info_state`（`onboarding_repository.py:99`）→ `ValueError`
- M-γ 阶段会统一切换到 `core.exceptions` 体系（见 `docs/roadmap/v0.3-product-skeleton.md`）

### 5.4 推荐使用方式

业务代码建议**自下而上捕获**：

```python
from backend.core.exceptions import (
    RealtimeNovelError,  # 基类
    LLMError,
    GenerationError,
    ProjectNotFoundError,
)

try:
    result = await generate_chapter(project_id, ...)
except ProjectNotFoundError:
    return JSONResponse({"error": "project_not_found"}, status_code=404)
except LLMError as e:
    return JSONResponse({"error": "llm_failed", "detail": str(e)}, status_code=502)
except GenerationQualityError as e:
    return JSONResponse({"error": "quality_fail", "detail": str(e)}, status_code=422)
except RealtimeNovelError as e:
    # 兜底：所有产品异常
    return JSONResponse({"error": "internal", "detail": str(e)}, status_code=500)
```

### 5.5 不要混用

- ❌ 业务代码不要抛 `Exception` / `RuntimeError` 等系统异常
- ❌ 不要用 `assert` 做业务校验（assert 可被 `python -O` 关掉）
- ✅ 业务校验失败 → 抛 `core.exceptions` 子类
