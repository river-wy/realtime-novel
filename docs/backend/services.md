# 后端业务编排层文档

> **更新日期**：2026-07-02
> **版本**：v0.9.6
> **Commit**：e717e5b
> **代码定位**：`backend/services/`

---

## 目录

1. [业务编排层定位](#1-业务编排层定位)
2. [ProjectManager](#2-projectmanager)
3. [OnboardingFlow（DEPRECATED）](#3-onboardingflowdeprecated)
4. [OnboardingArtifacts](#4-onboardingartifacts)
5. [ConsistencyChecker](#5-consistencychecker)
6. [CoverImageGenerator](#6-coverimagegenerator)
7. [InterventionParser](#7-interventionparser)
8. [业务流示例](#8-业务流示例)

---

## 1. 业务编排层定位

`backend/services/` 是「**业务编排层**」，位于 `persistence`（数据层）和 `agent`（推演层）之间。

### 1.1 与 agent 层的边界

| 维度 | services（编排） | agents（推演） |
|------|-----------------|---------------|
| 职责 | 多步骤业务流程串联、状态机管理、副作用落库 | LLM 调用、ReAct 循环、工具路由 |
| 触发 | API 路由 / EventBus 钩子 | LLM 决策 + tools 列表 |
| LLM 知识 | 0（不调 LLM） | 调 LLM / 调 services |
| 状态机 | Onboarding / 项目生命周期 | 章节生成 FSM |
| 代表类 | ProjectManager, OnboardingFlow, ConsistencyChecker | ButlersAgent, NovelWriterAgent, WorldTreeMaker |

**铁律**：services 调 persistence + utils；services 调 LLM 仅在 `cover_image_generator`（特例）。agents 调 services；agents 之间不直连（走 `sessions_send`）。

### 1.2 模块依赖图

```
API (FastAPI routers)
  ├── ProjectManager  ──→ ProjectRepository / ChapterRepository / ChapterStatusRepository
  ├── OnboardingFlow  ──→ OnboardingRepository
  ├── OnboardingArtifacts ──→ OnboardingRepository / ProjectRepository + EventBus
  ├── ConsistencyChecker ──→ ProjectRepository
  ├── CoverImageGenerator ──→ LLMAdapter (Gemini)
  └── InterventionParser ──→ ChapterRepository

Agent (ReAct loop)
  ├── ButlersAgent (管家)
  ├── NovelWriterAgent (文笔家)
  ├── WorldTreeMakerAgent (WTM)
  └── StyleMakerAgent (文风家)
  └── 调 services + 调 LLM
```

---

## 2. ProjectManager

`backend/services/project_manager.py`

### 2.1 职责

项目级 CRUD + 软删除 + 回档 + trash 恢复 + 详情加载。是 `projects` 表的「门面」。

### 2.2 关键方法

| 方法 | 行号 | 职责 |
|------|------|------|
| `create(name, exploration_level)` | 36 | 生成 `world-{8hex}` ID，写 DB + 建 `data/projects/{id}/` 目录 + 建 `chapters/` 子目录 |
| `update_exploration_level(project_id, level)` | 65 | 切换 `conservative/standard/wild`，`ProjectNotFound` 时 `raise FileNotFoundError` |
| `load(project_id)` | 71 | 加载项目详情 + 过滤已软删 + 拼装 `chapters` 列表 + 拼装 `seven_artifacts` + 读 `onboarding_state` |
| `list_projects(limit, offset)` | 132 | 列项目（自动跳过软删） + 附 `chapter_count` + `onboarding_step` + `status` 字段 |
| `update_base(project_id, key, new_value)` | 161 | 改 6 件基座（**v003 残留方法**，调用 `_load_one` 走 `load_all_artifacts`，已不推荐使用） |
| `_load_one(project_id, key)` | 197 | 内部 helper：从 `load_all_artifacts` 取单件 |
| `rollback(project_id, to_chapter, confirm=False)` | 211 | 回档到指定章节（cascade DB + 删文件），**必须 confirm=True** |
| `soft_delete(project_id, confirm=False)` | 244 | 调 `delete` + 打日志 |
| `delete(project_id, confirm=False)` | 251 | `shutil.move` 到 `.trash/` + `soft_delete` + `hard_delete`（**FK CASCADE 清 17 张表**） |
| `restore(trash_name)` | 281 | 从 `.trash/{name}/` 移回 `projects/{id}/` + `restore_delete` 清 `deleted_at` |

### 2.3 依赖

- `ProjectRepository`, `ChapterRepository`, `ChapterStatusRepository`, `OnboardingRepository`
- `shutil`, `asyncio.to_thread`（避免阻塞事件循环）
- 不调 LLM

### 2.4 调用位置

- `backend/api/project_routes.py`：所有 `/api/projects/*` 路由
- `backend/api/action_routes.py`：项目操作动作（rollback / delete / restore）

### 2.5 关键约定

- **v003 删除 palette 入参**（`project_manager.py:38`）：`palette` 仅响应回填给前端，不入 `projects` 表
- **软删项目过滤**（`project_manager.py:78`）：`load()` 发现 `deleted_at` 非空返 `None`
- **回档安全门**：`confirm=False` 直接 `raise ValueError`，必须显式确认
- **status 字段**（`project_manager.py:152`）：根据 `chapter_count` + `onboarding_step` 推 `"completed"` / `"in_progress"` / `"not_started"`

---

## 3. OnboardingFlow（DEPRECATED）

`backend/services/onboarding_flow.py`

### 3.1 状态

**v003 完整废弃 5 步流程**（`onboarding_flow.py:1-11` docstring）。

保留原因：
- `step()` / `load_state()` 保留但无调用方（兜底）
- `update_project_name_in_state()` 仍被 `onboarding_hooks` 调用（项目名同步到 onboarding_state）

### 3.2 新流程

v0.8 起：管家 ReAct 自由对话 → `verify_world_tree_baseline` 校验 → `delegate_to_wtm` 委托 WTM → 详见 `onboarding_tools.py` 与 `arch-plan/onboarding-pipeline.md`。

### 3.3 关键方法（保留）

| 方法 | 职责 |
|------|------|
| `load_state(project_id)` | 读 onboarding_state 的 `state_json`（v003 实际优先 `payload_json`） |
| `step(project_id, step, payload)` | **DEPRECATED**，原 5 步状态机入口。Step 2 写 `palette`（已废弃），Step 5 调 `delegate_chapter_generation` 生成第 1 章 |
| `update_project_name_in_state(project_id, new_name)` | 把自动生成的项目名写 `state_json.project_name`，由 `onboarding_hooks` 在 Step 4 完成时调 |

### 3.4 依赖

- `OnboardingRepository`, `ProjectRepository`
- v0.3 旧 `delegate_chapter_generation`（保留 HTTP 路由兜底）

### 3.5 调用位置

- `backend/api/action_routes.py`：仅在 `step == "5"` 兜底路径
- `backend/agent/onboarding_hooks.py`：Step 4 完成后调 `update_project_name_in_state`

---

## 4. OnboardingArtifacts

`backend/services/onboarding_artifacts.py`

### 4.1 职责

**WTM 基座状态机 + 完整性校验**。v0.8 起替代旧 5 步流程的「Step 4 委托 WTM」环节。

### 4.2 关键方法

#### 状态机切换（3 个）

| 函数 | 行号 | 职责 |
|------|------|------|
| `mark_wtm_pending(project_id)` | 19 | 委托前调：`info_state = 'wtm_pending'` |
| `mark_wtm_baseline_ready(project_id)` | 27 | 委托成功：`info_state = 'ready'` + **emit `onboarding.step4_confirmed` 事件** |
| `mark_wtm_baseline_failed(project_id, error)` | 50 | 委托失败：`info_state = 'collecting'`（回退，管家继续对话） |

`mark_wtm_baseline_ready` 内部用 `asyncio.get_event_loop().create_task(...)` 同步触发 `event_bus.emit`（`onboarding_artifacts.py:38`），fire-and-forget，事件钩子（如生成项目名 + 封面图）在后台并发跑。

#### 完整性校验（1 个）

`verify_world_tree_baseline(project_id) -> {ready, missing_items, all_items}`

`onboarding_artifacts.py:64` — spec §5.6 6 项校验：

1. `world_tree.story_core` 非空
2. `world_tree.genre_tags_json` 非空
3. `world_tree.core_rules_json` 非空
4. `characters` 至少 1 个 `protagonist`
5. `main_plot` 至少 1 个 `pending` 节点
6. `volumes` 至少 1 个卷

返回 `ready=True` 当且仅当 6 项都通过。管家在委托 WTM 前调（看缺什么） + WTM 完成后调（二次确认）。

#### 工具函数（3 个）

| 函数 | 职责 |
|------|------|
| `merge_payload_to_state(project_id, step, fields)` | 调 `OnboardingRepository.merge_payload` |
| `load_payload(project_id)` | 从 `payload_json` 读完整 dict |
| `get_onboarding_info_state(project_id)` | 读 `info_state` 字符串 |

### 4.3 依赖

- `OnboardingRepository`, `ProjectRepository`
- `EventBus.emit("onboarding.step4_confirmed")`

### 4.4 调用位置

- `backend/agent/delegation_tools.py`：调 3 个状态机切换
- `backend/agent/tools/butler_tools.py`：管家委托 WTM 前后调 `verify_world_tree_baseline`
- `backend/agent/onboarding_hooks.py`：订阅 `onboarding.step4_confirmed` 事件

### 4.5 完整链路（v0.8）

```
管家 ReAct → 收集足够 hint
  → delegate_to_agent(agent=WTM, intent=initial_baseline, payload=...)
    → delegation_tools._delegate_wtm_initial_baseline 调 mark_wtm_pending
    → WTM.run_initial_baseline_react (走 ReAct 自主落库 9 张表)
      → 成功：delegation_tools 调 mark_wtm_baseline_ready
                → event_bus.emit("onboarding.step4_confirmed")
                  → onboarding_hooks.handle_step4_confirmed
                    → 生成项目名 + 调 generate_and_save_cover
      → 失败：delegation_tools 调 mark_wtm_baseline_failed
  → 管家收到结果 → 整合回复用户
```

---

## 5. ConsistencyChecker

`backend/services/consistency_checker.py`

### 5.1 职责

**两阶段一致性检查器**（v003 重构）：
- 阶段 1 `check_hard_rules`：**硬约束违例扫描**（致命可阻断）
- 阶段 2 `check_world_entries`：**知识矛盾扫描**（警告不阻断）

### 5.2 关键方法

#### `check_hard_rules(chapter_text, character_actions) -> HardRuleViolationResult`

`consistency_checker.py:73`

读 `world_tree.core_rules_json`，筛 `enforcement="hard"` 的规则，对照章节文本 + 角色动作扫描。

**当前实现的 3 类硬约束**（`consistency_checker.py:107-150`）：

| 规则 | 检测方式 |
|------|---------|
| 无魔法 / `no magic` | 角色 action 含「魔法/wizard/spell」 + 章节文本含「魔法/spell」 |
| 古代 / 架空时代 | 章节文本含「卧槽/666/哈哈哈/OMG/lol/yyds」等现代网络词 |
| 禁止穿越 / `no time travel` | 章节文本含「穿越/time travel」 |

返回 `HardRuleViolation { rule_id, rule_statement, violation_type, message, related_char_id, related_text }` 列表 + `has_fatal` 布尔。

#### `check_world_entries(chapter_text, category=None) -> WorldEntryConflictResult`

`consistency_checker.py:158`

读 `world_entries` 表（可选按 `category` 过滤），对每条 `content` 做关键词匹配。

**当前实现的检测**（`consistency_checker.py:189`）：用正则 `(\d+)([\u4e00-\u9fa5]+) = (\d+)([\u4e00-\u9fa5]+)` 提取「金=银/铜/元/币」等数字关系，检查章节文本是否出现相反关系（如「10 银 = 1 金」与「1 金 = 10 银」矛盾）。

返回 `WorldEntryConflict { entry_id, entry_title, conflict_type, message }` 列表 + `has_warnings` 布尔。

### 5.3 依赖

- `ProjectRepository`（`get_core_rules` + `list_world_entries`）
- 不调 LLM

### 5.4 调用位置

- `backend/agent/agents/novel_writer.py`：章节生成后调（hard_rules 阻断 + world_entries 警告）
- 未来可接入 `backend/api/chapter_routes.py` 的预览/校验

### 5.5 扩展点

- LLM-based 检测：可后续扩展为调 LLM 做语义级矛盾扫描（当前是字符串 + 正则）
- 规则定义：当前 3 类硬约束写死，可改为读 `core_rules_json.statement` 全文匹配

---

## 6. CoverImageGenerator

`backend/services/cover_image_generator.py`

### 6.1 职责

**世界封面图生成服务**。v0.9 起，onboarding Step 4 完成后并发调 Gemini 生图。

### 6.2 关键方法

| 方法 | 行号 | 职责 |
|------|------|------|
| `build_cover_prompt(payload)` | 23 | 从 onboarding payload 构建 prompt（`story_core/characters/genres/tone`） |
| `generate_and_save_cover(project_id, payload, projects_root)` | 51 | 生成 + 保存 + 返回静态 URL（失败返 None） |

### 6.3 流程

`cover_image_generator.py:68`

```
1. build_cover_prompt(payload)  # 套 COVER_IMAGE_PROMPT_TEMPLATE
2. adapter = get_llm_adapter()
3. result = await adapter.generate_image(prompt, aspect_ratio="1:1", image_size="1K")
4. image_data = result["image_urls"][0]
5. 判断是 URL 还是 base64：
   - URL → httpx 下载
   - base64 → 补 padding → b64decode
6. cover.png 写入 data/projects/{id}/cover.png
7. 返回 "/static/projects/{id}/cover.png"
```

### 6.4 依赖

- `LLMAdapter.generate_image`（走 Router → `GeminiProvider`）
- `httpx.AsyncClient`（下载 URL 模式）
- `base64`（解码 inline data）

### 6.5 调用位置

- `backend/agent/onboarding_hooks.py`：订阅 `onboarding.step4_confirmed` 事件时调

### 6.6 失败处理

异常（生成失败 / base64 解码失败 / 写文件失败）全部 catch 并 log，`return None`。调用方在 `None` 时跳过封面图更新（不阻断 onboarding）。

### 6.7 配套前端推送

`cover_image_generator.py:128` 返回静态 URL，由 `onboarding_hooks` 调 `projects.cover_image_url` 写入 + 推 WS 事件 `cover_image_updated` 给前端。

---

## 7. InterventionParser

`backend/services/intervention_parser.py`

### 7.1 职责

**剧情干预解析器**。用户在前端输入「下一章要 XX」类的干预，写到最新章节的 `intervention` 字段，下一章生成时读出作为 prompt 上下文。

### 7.2 关键方法

`add(project_id, intervention) -> {accepted, chapter_num?, reason?}`（`intervention_parser.py:19`）

```
1. latest = chapter_repository.get_latest(project_id)
2. if not latest: return {accepted: False, reason: "no chapter yet"}
3. chapter_repository.update_intervention(
       project_id=project_id,
       chapter_num=latest.chapter_num,
       intervention=intervention,
   )
4. return {accepted: True, chapter_num: latest.chapter_num}
```

### 7.3 依赖

- `ChapterRepository.get_latest` + `update_intervention`

### 7.4 调用位置

- `backend/api/action_routes.py`：`POST /api/projects/{id}/intervention`

### 7.5 v003 变更

**删除** `actor_feedback / actor_character` 入参（`intervention_parser.py:6` docstring）。干预只走 `chapters.intervention` 字段。

### 7.6 章节生成时读干预

由 `NovelWriterAgent` 在组装 context 时从 `latest_chapter.intervention` 字段读出作为 prompt 段落。

---

## 8. 业务流示例

### 8.1 创建项目 + Onboarding 完整走完

```
[User] POST /api/projects {"name": "九州仙侠传", "exploration_level": "standard"}
       ↓
[ProjectManager.create]
  ├── project_id = "world-3f7a8b2c"
  ├── ProjectRepository.create
  ├── mkdir data/projects/world-3f7a8b2c/chapters
  └── return {id, name, exploration_level}

[管家 ButlersAgent 启动]
  ├── OnboardingRepository.get_info_state → "collecting"
  ├── 自由对话收集：用户说「修仙题材」「主角是少年剑客」「基调热血」
  └── 管家调 verify_world_tree_baseline(project_id)
        ↓
[OnboardingArtifacts.verify_world_tree_baseline]
  ├── 读 world_tree (空) → story_core 缺
  ├── 读 characters (空) → 缺
  ├── 读 main_plot (空) → 缺
  ├── 读 volumes (空) → 缺
  └── return {ready: False, missing_items: [...]}

[管家继续对话补全 hint]
  ├── 调 delegation_tools.delegate_to_agent(WTM, initial_baseline, payload)
        ↓
[OnboardingArtifacts.mark_wtm_pending]
  └── OnboardingRepository.set_info_state("wtm_pending")

[WTM.run_initial_baseline_react]
  ├── 自主调工具落库 9 张表
  │   ├── save world_tree
  │   ├── save characters
  │   ├── save main_plot
  │   ├── save volumes
  │   ├── save sub_plot
  │   ├── save timeline_events
  │   ├── save geography_locations
  │   ├── save world_entries
  │   └── save core_rules
  └── 成功 → 调 mark_wtm_baseline_ready
        ↓
[OnboardingArtifacts.mark_wtm_baseline_ready]
  ├── OnboardingRepository.set_info_state("ready")
  └── event_bus.emit("onboarding.step4_confirmed", project_id=project_id)
        ↓ (后台并发)
[Onboarding Hooks]
  ├── handle_step4_confirmed(project_id)
  │   ├── 自动生成项目名（调 LLM）
  │   ├── OnboardingFlow.update_project_name_in_state
  │   ├── generate_and_save_cover(project_id, payload, projects_root)
  │   │   └── LLMAdapter.generate_image → GeminiProvider → 写 cover.png + 推 WS
  │   └── ProjectRepository.update_cover_image_url
  └── ...

[管家二次确认]
  └── verify_world_tree_baseline → ready: True
  └── return "基座已就绪，是否生成第 1 章？"

[User] "生成第 1 章"
       ↓
[NovelWriterAgent]
  ├── 读 7 件基座 + 5 件 history
  ├── 组装 prompt（含 chapters.latest.intervention = None）
  ├── LLMAdapter.stream → DeepSeekProvider.stream
  ├── ConsistencyChecker.check_hard_rules (阻断扫描)
  ├── ConsistencyChecker.check_world_entries (警告扫描)
  ├── ChapterRepository.create
  │   ├── 写 data/projects/{id}/chapters/chapter_001.md
  │   └── 落 DB
  ├── ChapterStatusRepository.set_status("done")
  └── 推 WS chapter_generated
```

### 8.2 用户对生成结果不满意，触发回档

```
[User] POST /api/projects/{id}/rollback {"to_chapter": 3, "confirm": true}
       ↓
[ProjectManager.rollback]
  ├── 校验 confirm=True
  ├── chapter_repository.rollback_to(to_chapter=3)
  │   └── DELETE FROM chapters WHERE chapter_num > 3
  ├── ChapterStatusRepository.delete_after_chapter(keep_up_to=3)
  │   └── DELETE FROM chapter_status WHERE chapter_num > 3
  ├── 遍历 chapters_dir/chapter_*.md：删 num > 3 的文件
  └── return {kept_chapters: 3, removed_chapters: N}

[后续重新生成]
  ├── NovelWriterAgent 从第 4 章开始
  └── 7 件基座 / 角色 / 卷 / 伏笔不动
```

### 8.3 用户想删除项目

```
[User] DELETE /api/projects/{id}?confirm=true
       ↓
[ProjectManager.delete]
  ├── shutil.move(data/projects/{id} → data/projects/.trash/{id}-{timestamp})
  ├── ProjectRepository.soft_delete (deleted_at = now)
  └── ProjectRepository.hard_delete
        └── FK CASCADE 清 17 张表（world_tree / characters / seeds / chapters / ...）
  └── return {trash_path, deleted_at}

[7 天内反悔]
  └── ProjectManager.restore(trash_name)
        ├── shutil.move(.trash/{id}-{ts} → projects/{id})
        └── ProjectRepository.restore_delete (deleted_at = NULL)
        └── ⚠️ 注意：DB 已 hard_delete 清空，restore 后只剩文件
```
