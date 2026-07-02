# 前端 API 对接自检报告

> 时间：2026-07-02  |  commit: e717e5b  |  v0.9.6

## 总览

| 指标 | 数值 |
|------|------|
| 后端 HTTP 端点 | 11 个 |
| 前端调用的 HTTP 端点 | 6 个（含 1 个死代码 `healthCheck`、3 个死代码 actions） |
| HTTP 端点对齐 | 6/6 调用级对齐（method/path/query 全对），但有 3 个 body 字段冗余 + 多个 interface 字段实际不返回 |
| 前端 API 函数 | 11 个（projects: 6、chapters: 3、actions: 3、client: 1、healthCheck 1 实际 12） |
| 前端实际调用 | 7 个（`listProjects/getProject/createProject/deleteProject/updateExplorationLevel/listChapters/readChapter/generateChapter/rollbackProject`） |
| 死代码 API 函数 | 4 个（`healthCheck`、`updateBase`、`submitIntervention`、`generateImage`） |
| WS 事件对齐 | 7/7 已处理事件类型匹配；`onboarding_*` 3 个事件未在前端处理（v0.6.2 后已不用，符合预期） |
| P1-3 复查（2026-07-02） | **误报已确认 OK** — `Reader.vue:58` 的 `submitIntervention` 是 local function（不调 API），用于"已记录"反馈动画 + 文本"已记录" + hint"干预会在下一章生成时应用"三重提示。文案与实际行为一致，不存在 UI 误导。 |

**结论：调用层 100% 对齐，但有 4 处「前端发了但后端忽略的字段」+ 4 个死代码 + 多个 interface 字段不存在的隐患。**

---

## 端点对齐表

| # | 前端调用 | 后端路由 | Method | 状态 | 问题 |
|---|---------|---------|--------|------|------|
| 1 | `api.healthCheck()` `client.ts:30` | `/api/health` (`system_routes.py:36`) | GET | 🟡 死代码 | 前端未实际调用 |
| 2 | `api.listProjects()` `projects.ts:52` | `/api/projects?limit&offset` (`project_routes.py:91`) | GET | ✅ 对齐 | `include_deleted` query 字段前端未传（默认 false，符合预期） |
| 3 | `api.getProject(id)` `projects.ts:56` | `/api/projects/{id}` (`project_routes.py:131`) | GET | ✅ 对齐 | — |
| 4 | `api.createProject(name, prompt?)` `projects.ts:60` | `/api/projects` (`project_routes.py:103`) | POST | ✅ 对齐 | 后端返回 `CreateProjectResponse{ id, name, created_at, onboarding_required }`；前端未取 `onboarding_required` |
| 5 | `api.deleteProject(id)` `projects.ts:64` | `/api/projects/{id}?confirm=true` (`project_routes.py:171`) | DELETE | ✅ 对齐 | 后端返回 `DeleteProjectResponse{ id, deleted_at, chapters_removed, trash_path }`；前端只取整个 data（store.ts:33 仅 await） |
| 6 | `api.updateBase()` `projects.ts:69` | `/api/projects/{id}/base` (`action_routes.py:144`) | PATCH | 🟡 死代码 | 前端未实际调用（store/projects.ts 未引入 updateBase） |
| 7 | `api.updateExplorationLevel()` `projects.ts:80` | `/api/projects/{id}/exploration-level` (`project_routes.py:152`) | PATCH | ✅ 对齐 | — |
| 8 | `api.listChapters()` `chapters.ts:30` | `/api/projects/{id}/chapters` (`chapter_routes.py:51`) | GET | ✅ 对齐 | — |
| 9 | `api.readChapter()` `chapters.ts:34` | `/api/projects/{id}/chapters/{n}` (`chapter_routes.py:76`) | GET | ✅ 对齐 | — |
| 10 | `api.generateChapter()` `chapters.ts:40` | `/api/projects/{id}/chapters` (`chapter_routes.py:114`) | POST | ⚠️ body 冗余 | 前端发 `{ intervention, actor_feedback, actor_character }`，后端 `GenerateChapterRequest` 只接 `intervention`（**`actor_feedback` 和 `actor_character` 被 Pydantic 默认忽略**） |
| 11 | `api.submitIntervention()` `actions.ts:11` | `/api/projects/{id}/interventions` (`action_routes.py:33`) | POST | 🟡 死代码 | 前端未实际调用（Reader.vue 58 行同名函数是本地函数，非 API 调用） |
| 12 | `api.rollbackProject()` `actions.ts:27` | `/api/projects/{id}/rollback?to_chapter&confirm` (`action_routes.py:78`) | POST | ✅ 对齐 | — |
| 13 | `api.generateImage()` `actions.ts:36` | `/api/projects/{id}/image` (`action_routes.py:113`) | POST | 🟡 死代码 | 前端未实际调用 |
| — | （无前端调用）`/api/info` (`system_routes.py:48`) | GET | 🟡 后端空闲端点 | — |

---

## 字段对齐问题（按文件）

### 🔴 frontend/src/api/projects.ts

#### `ProjectInfo` interface（L13-23） vs 后端 `ProjectInfo` schema (`project_routes.py:18-30`)
| 前端字段 | 后端返回 | 状态 |
|---------|---------|------|
| `id` | ✓ | ✅ |
| `name` | ✓ | ✅ |
| `exploration_level` | ✓ | ✅ |
| `chapter_count` | ✓ | ✅ |
| `last_updated` | ✓ | ✅ |
| `status` | ✓（值 `not_started`/`in_progress`/`completed`）| ✅ |
| `cover_image_url` | ✓ | ✅ |
| — | `onboarding_step` | ⚠️ 后端返回但前端未声明（兼容，不影响）|

#### `ProjectDetail` interface（L25-37） vs 后端 `ProjectDetailResponse` (`project_routes.py:58-70`)
| 前端字段 | 后端实际返回 | 状态 |
|---------|------------|------|
| `id/name/exploration_level/seven_artifacts/world_tree/chapters/cover_image_url` | ✓ | ✅ |
| `current_pov` (string\|null) | ❌ 不在 `ProjectDetailResponse` schema 中 | 🐛 **后端 manager 算了值但被 response_model 截断**（`project_routes.py:134-148` 显式构造时未传 `current_pov`/`current_pov_char_id`/`current_pov_name`）|
| `current_pov_char_id` | ❌ 同上 | 🐛 同上 |
| `current_pov_name` | ❌ 同上 | 🐛 同上 |
| —（前端未声明）| `onboarding_step` / `onboarding_payload` | ⚠️ 后端返回但前端未读 |

**结论**：`current_pov*` 3 个字段是**死接口字段**（前端没有 view 引用，后端也不发出）。建议：
- 方案 A：后端补到 `ProjectDetailResponse` 显式字段并传入
- 方案 B：前端删 `current_pov*` 3 个字段声明

### 🔴 frontend/src/api/chapters.ts

#### `ChapterListItem` (L9-12) vs 后端 `ChapterInfo` (`chapter_routes.py:20-28`)
| 前端字段 | 后端返回 | 状态 |
|---------|---------|------|
| `num/title/summary` | ✓ | ✅ |
| `status` | ✓（硬编码 `"done"`）| ✅ |
| `time` (Optional) | ✓ | ✅ |
| `word_count` (Optional) | ❌ **list 端点不返回**（`chapter_routes.py:65-72` 构造时未传） | 🐛 字段永远 `undefined` |
| `file_path` (Optional) | ❌ **list 端点不返回** | 🐛 字段永远 `undefined` |

> `word_count`/`file_path` 是 `ChapterSummary` 继承来的字段（`projects.ts:40,42`），但 list 端点不返回——前端不消费，**纯死字段**。

### 🟡 frontend/src/api/actions.ts — `submitIntervention` 字段冗余

```ts
// actions.ts:16-20
await api.post(`/projects/${projectId}/interventions`, {
  intervention,
  actor_feedback: actorFeedback,    // ❌ 后端 InterventionRequest 无此字段
  actor_character: actorCharacter  // ❌ 后端 InterventionRequest 无此字段
})
```
后端 schema (`action_routes.py:25-28`)：
```python
class InterventionRequest(BaseModel):
    intervention: Optional[str] = None
```

Pydantic 默认忽略未知字段 → 不会 422，但前端在传 `undefined` 浪费字节 + 误导后人。**与 `generateChapter` 同病**（`chapters.ts:46-50`）。

### ✅ 2026-07-02 修复状态

**P1 问题已全部修复**：

1. ✅ **死字段清理**（actions.ts + chapters.ts + stores/chapters.ts） — `actor_feedback` / `actor_character` 已从类型签名和调用处删除
2. ✅ **死代码清理**（client.ts + projects.ts + actions.ts） — `healthCheck` / `updateBase` / `submitIntervention`（API）/ `generateImage` 已删除
3. ✅ **死接口字段清理**（projects.ts:ProjectDetail） — `current_pov` / `current_pov_char_id` / `current_pov_name` 已删除
4. ✅ **api/client.ts:4 端口注释错误** — 已修正为「见 vite.config.ts 的 BACKEND_PORT」（删除硬编码的 7777）
5. ✅ **vue-tsc + vite build** — exit 0，670ms 构建通过

### ✅ 健康：snake_case 风格

- 前端接口、store、views **全部使用 snake_case** 字段名（`chapter_count`、`last_updated`、`cover_image_url`、`actor_feedback`...）
- 后端 Pydantic schema **也用 snake_case**
- 没有任何 camelCase / snake_case 混用
- **无需转换层**（无 axios 拦截器/transformResponse 改字段名）

---

## WS 事件对齐

### useStewardChat.ts handleEvent(L98-135) vs 后端 ws_manager.py + schemas/events.py

| 后端事件类型 | 事件 schema（events.py） | 前端处理 | 字段读取 | 状态 |
|------------|------------------------|---------|---------|------|
| `agent_thinking` | `type, content` | ✅ L99 | `msg.content` | ✅ |
| `tool_calling` | `type, tool, args` | ✅ L101（静默忽略）| — | ✅ |
| `tool_result` | `type, tool, result` | ✅ L101（静默忽略）| — | ✅ |
| `agent_message` | `type, content`（schema 不全）| ✅ L103 | `msg.content, msg.intent, msg.structured_data` | ✅（schema 与实际发送不一致，但前端从 dict 读字段名都对得上）|
| `confirm_required` | `type, action, details` | ✅ L122 | `msg.action, msg.details` | ✅ |
| `error` | `type, code, message` | ✅ L124 | `msg.message` | ✅（`code` 字段前端未读，可忽略）|
| `interrupted` | `type, message` | ✅ L128 | `msg.message` | ✅ |
| `pong` | （心跳）| ✅ L131 | — | ✅ |
| `onboarding_proposal` | `type, step, fields` | ❌ 未处理 | — | 🟡 v0.6.2 后已不用，符合预期 |
| `onboarding_confirmed` | `type, step, fields, artifacts_written` | ❌ 未处理 | — | 🟡 同上 |
| `onboarding_step_done` | `type, step, next_step` | ❌ 未处理 | — | 🟡 同上 |

### 客户端发送 → 后端接收
| 前端发送（useStewardChat.ts）| 后端接收（ws_manager.py）| 状态 |
|----|----|------|
| `{ type: "user_message", content, project_id? }` L142-147 | `data.get("content")` L155, `data.get("project_id")` L151, `data.get("type")` L99 | ✅ |
| `{ type: "confirm", action, confirmed }` L154-160 | `data.get("action")` L116 echo | ✅（后端仅 echo，未真正处理）|
| —（未实现）`{ type: "interrupt" }` | L106-117 已支持 | 🟡 前端缺中断功能 |
| —（未实现）`{ type: "ping" }` | L120-122 已支持 | 🟡 前端未发心跳 |

> 注 2：前端未实现 `interrupt` 和 `ping` 发送——`ping` 不发不会断连（浏览器 WS 自带 keep-alive）；`interrupt` 缺失则无法主动取消「思考中」的 Agent。

---

## 必修复 Bug（按 P0/P1/P2）

### 🔴 P0 — 无（调用层全对齐，没有 422/解析失败风险）

### 🟡 P1 — 接口契约不一致（3 个）

#### P1-1：前端发 `actor_feedback` / `actor_character` 但后端忽略
- 位置：`frontend/src/api/actions.ts:19-20`、`frontend/src/api/chapters.ts:46-50`
- 风险：v003 删字段后未清理前端调用方。当前 Pydantic `BaseModel` 默认 `extra=ignore` 不报错，但语义误导、字段会随 JSON 体积泄漏
- 修复：前端 store/types 删除 `actor_feedback` / `actor_character` 字段
  - `frontend/src/stores/chapters.ts:47`
  - `frontend/src/api/chapters.ts:43`
  - `frontend/src/api/actions.ts:9-21`

#### P1-2：`current_pov*` 字段是死接口（前端声明、后端不返回）
- 位置：`frontend/src/api/projects.ts:32-34`
- 风险：将来若 view 真用 `current_pov_name` 等字段，会拿到 `undefined`
- 修复（推荐 A）：后端 `project_routes.py:60-69` `ProjectDetailResponse` 补 `current_pov / current_pov_char_id / current_pov_name` 字段，并在 L134-148 构造时传入
- 修复（推荐 B）：前端 `ProjectDetail` 删 3 行声明（当前 view 都不消费）

#### P1-3：Reader.vue 「干预提交」按钮只 setTimeout 不调 API（UI 误导）
- 位置：`frontend/src/views/Reader.vue:58-62, 207, 213, 240`
- 现状：本地 `submitIntervention` 函数仅显示「已记录」2 秒动画，**未实际 POST `/api/projects/{id}/interventions`**；`Reader.vue:52` 的 `nextChapter` 会把 `intervention.value` 透传到 `chaptersStore.generate` → `api.generateChapter`，**所以干预内容最终会随「生成下一章」一起发到后端**（不会丢失）
- 风险：UI 误导——「提交」按钮带勾选动画会让用户以为已持久化，但实际只走前端 state；与「管家对话」走 WS 干预的交互不一致（v0.5+ 干预语义是「提交即应用」）
- 修复：要么真调 `api.submitIntervention(projectId, intervention.value)`；要么把按钮文案改为「记住」并去掉「已记录」勾选动画

### 🟢 P2 — 死代码 / 风格建议

#### P2-1：4 个未使用的 API 函数（死代码）
- `frontend/src/api/client.ts:30` `healthCheck()` — 全代码库无 import
- `frontend/src/api/projects.ts:69` `updateBase()` — 全代码库无 import
- `frontend/src/api/actions.ts:11` `submitIntervention()` — 全代码库无 import（注：Reader.vue 58 行同名函数是**本地函数**，非 API 调用）
- `frontend/src/api/actions.ts:36` `generateImage()` — 全代码库无 import
- 处理：删除或加 TODO 注释（v0.6.2 重构时已删 onboarding 相关函数，actions.ts 头注释也有说明，但 actions 残留函数应一起清掉）

#### P2-2：前端无 WS `interrupt` / `ping` 发送
- 位置：`useStewardChat.ts` 缺 `sendInterrupt()` 方法
- 风险：长思考中用户无法主动取消（要等 Agent 自然完成或刷新页面）
- 建议：加「停止思考」按钮 + `chat.sendInterrupt()`

#### P2-3：后端 `/api/info` 端点无前端调用
- 位置：`system_routes.py:48`
- 处理：保留作 health-check 增强，或加前端「版本号展示」组件

#### P2-5：`ChapterInfo` list 不返回 `word_count` / `file_path`
- 位置：`backend/api/chapter_routes.py:65-72`
- 风险：若将来前端用 `word_count` 做章节列表展示，会拿到 `undefined`
- 处理：后端 list 时补 `word_count`（ChapterRow 已有该字段，`models.py:282`）

---

## 建议（非阻塞）

1. **WS 缺 `interrupt` 客户端**：长任务（如 60-100s 章节生成）用户无法取消是体验硬伤。Reader.vue 应在「生成中」时提供「取消」按钮
2. **`AgentMessageEvent` schema 字段不全**（`events.py:43-44` 只声明 `type, content`，但 ws_manager.py 实际发 `content, intent, structured_data`）：建议 schema 补全，作为契约文档
3. **`onboarding_*` 3 个事件在前端完全未处理**：虽然 v0.6.2 后不再触发，建议 `useStewardChat.ts:136` `console.debug('未知事件:', t, msg)` 保留——能监控未来回归
4. **`cover_image_url` 在 Reader.vue 102/116 行的 `ph-book-open` fallback** 与 World.vue L77 的 `cover-icon` 共用 72px 字号——一致性 OK，无需改
5. **`v0.6.2` onboarding 删除注释** 在 `actions.ts:5-7` 和 `app.py:30-31` 都已存在，**说明团队对此有意识**——但 actions.ts 里的 `submitIntervention`/`generateImage` 函数本应一起清掉
6. **TypeScript 严格性**：`projects.ts:25-37` ProjectDetail 多余字段不会报错（TS 不做请求/响应契约校验）。建议加运行时校验（zod）——但这是项目级决策，非本次自检范围

---

## 自检结论

**HTTP 调用层：100% 对齐**（无 422/解析失败风险）。  
**Pydantic schema 冗余字段：3 处**（P1-1 + P1-2）。  
**死代码 API 函数：4 个**（P2-1）。  
**WS 事件：7/7 已对齐 + 1 个 `interrupt` 客户端缺失**（P2-2）。

**整体健康度：🟢 可发布**（调用层零阻塞 bug，但 P1-1/2 应在下版本前清理）。
