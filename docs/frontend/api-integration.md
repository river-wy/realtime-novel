# 前端 API 集成（v0.9.6）

> **版本**：v0.9.6  |  **commit**: e717e5b  |  **最后更新**：2026-07-02
>
> 本文档是前端的「HTTP API + WebSocket」集成手册。HTTP 部分以表格列出端点、签名、DTO；WS 部分（管家对话）展开事件处理逻辑与连接生命周期。
>
> 调用层对齐自检见 `docs/frontend/api-self-check.md`（P1/P2 问题清单）。

---

## 1. 元信息

| 项 | 值 |
|---|---|
| HTTP 客户端 | Axios ^1.7.9（`frontend/package.json:11`） |
| HTTP baseURL | `/api`（Vite proxy → `http://127.0.0.1:7778`，`vite.config.ts:25-28`） |
| HTTP timeout | 120 000 ms（章节生成最坏情况，`api/client.ts:16`） |
| WS 端点 | `ws://{window.location.host}/api/chat`（`composables/useStewardChat.ts:13`） |
| 后端 API 文档来源 | `backend/api/{app,ws_manager,project_routes,chapter_routes,action_routes,system_routes}.py` |

> **不要在前端硬编码后端端口**：所有 HTTP 走 `/api` 代理路径；WS 用 `window.location.host` 自动取当前域名。改端口只动 `vite.config.ts:19-20` 的 `FRONTEND_PORT` / `BACKEND_PORT` 两个常量。

---

## 2. HTTP API 集成层

### 2.1 Axios 实例配置

文件：`frontend/src/api/client.ts`

```ts
// client.ts:13-19
export const api: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 120_000,           // 章节生成最多 120s
  headers: { 'Content-Type': 'application/json' }
})
```

**响应拦截器**（`client.ts:22-29`）：

```ts
api.interceptors.response.use(
  response => response,
  (error: AxiosError) => {
    const detail = (error.response?.data as { detail?: string })?.detail
    if (detail) {
      error.message = detail   // 把后端 FastAPI HTTPException(detail=...) 提到 error.message
    }
    return Promise.reject(error)
  }
)
```

**作用**：业务层 catch 到的 `error.message` 永远是后端的 `detail` 文案（如 `"Project not found: xxx"`），无需手动 `error.response.data.detail` 解包。

---

### 2.2 Projects API（5 端点 + 1 死代码）

文件：`frontend/src/api/projects.ts`

| # | Method | 端点 | 函数签名 | 后端路由 |
|---|---|---|---|---|
| 1 | GET | `/api/projects?limit&offset` | `listProjects(limit=20, offset=0) → { total, projects: ProjectInfo[] }` | `project_routes.py:91` |
| 2 | GET | `/api/projects/{id}` | `getProject(id) → ProjectDetail` | `project_routes.py:131` |
| 3 | POST | `/api/projects` | `createProject(name, palette, initialPrompt?) → { id, name, created_at, onboarding_required }` | `project_routes.py:103` |
| 4 | DELETE | `/api/projects/{id}?confirm=true` | `deleteProject(id) → DeleteProjectResponse` | `project_routes.py:171` |
| 5 | PATCH | `/api/projects/{id}/exploration-level` | `updateExplorationLevel(projectId, level) → { project_id, exploration_level, message }` | `project_routes.py:152` |
| 🟡 | PATCH | `/api/projects/{id}/base` | `updateBase(projectId, key, newValue)` | `action_routes.py:144`（**死代码**） |

**DTO（前端 TypeScript interface）**：

```ts
// projects.ts:13-23
interface ProjectInfo {
  id: string
  name: string
  palette: string                                           // ⚠️ list 端点硬编码返回 ""（见 api-self-check.md P2-4）
  exploration_level: 'conservative' | 'standard' | 'wild'   // v0.8+
  chapter_count: number
  last_updated: string | null
  status: 'not_started' | 'in_progress' | 'completed'       // v0.8.3+
  cover_image_url?: string | null                            // v0.9+
}

// projects.ts:25-37
interface ProjectDetail {
  id, name, palette, exploration_level: 同上
  seven_artifacts: Record<string, any> | null
  world_tree: Record<string, any> | null
  chapters: ChapterSummary[] | null
  cover_image_url?: string | null                            // v0.9+
  current_pov?: string | null                                // 🐛 死字段：后端不返回（见 api-self-check.md P1-2）
  current_pov_char_id?: string | null                        // 🐛 同上
  current_pov_name?: string | null                           // 🐛 同上
}

// projects.ts:39-45
interface ChapterSummary {
  num: number
  title: string
  summary?: string | null
  word_count?: number                                       // 🐛 list 端点不返回（见 P2-5）
  file_path?: string                                        // 🐛 同上
  time?: string
}
```

> 字段命名约定：**snake_case**（与后端 Pydantic schema 完全一致），**无需转换层**。见 `api-self-check.md`「snake_case 风格」段。

---

### 2.3 Chapters API（3 端点）

文件：`frontend/src/api/chapters.ts`

| # | Method | 端点 | 函数签名 | 后端路由 |
|---|---|---|---|---|
| 1 | GET | `/api/projects/{id}/chapters` | `listChapters(projectId) → { chapters: ChapterListItem[] }` | `chapter_routes.py:51` |
| 2 | GET | `/api/projects/{id}/chapters/{n}` | `readChapter(projectId, n) → ChapterContent` | `chapter_routes.py:76` |
| 3 | POST | `/api/projects/{id}/chapters` | `generateChapter(projectId, options?) → GenerateChapterResult` | `chapter_routes.py:114` |

**DTO**：

```ts
// chapters.ts:9-12
interface ChapterListItem extends Omit<ChapterSummary, 'time'> {
  status: string                  // 后端硬编码返回 "done"
  time?: string | null
}

// chapters.ts:14-20
interface ChapterContent {
  num: number
  title: string
  content: string
  word_count: number
  generated_at: string | null
}

// chapters.ts:22-30
interface GenerateChapterResult {
  chapter_num: number
  title: string
  content: string
  word_count: number
  generated_at: string
  new_seeds_triggered: number
  summary: string                 // v0.5+
}
```

> ⚠️ **P1-1 字段冗余**：`generateChapter` 的 `options` 类型声明 `{ intervention, actor_feedback, actor_character }`（`chapters.ts:36-38`），但后端 `GenerateChapterRequest`（`chapter_routes.py:34-36`）只接 `intervention`，`actor_feedback` / `actor_character` 被 Pydantic 默认忽略。**前端应删除这两个字段声明**（详见 `api-self-check.md` P1-1）。

---

### 2.4 Actions API（3 端点 + 2 死代码）

文件：`frontend/src/api/actions.ts`

| # | Method | 端点 | 函数签名 | 后端路由 | 状态 |
|---|---|---|---|---|---|
| 1 | POST | `/api/projects/{id}/interventions` | `submitIntervention(projectId, intervention?, actorFeedback?, actorCharacter?)` | `action_routes.py:33` | 🟡 死代码 + 字段冗余（`actor_feedback` / `actor_character` 后端忽略） |
| 2 | POST | `/api/projects/{id}/rollback?to_chapter&confirm` | `rollbackProject(projectId, toChapter)` | `action_routes.py:78` | ✅ |
| 3 | POST | `/api/projects/{id}/image` | `generateImage(projectId, styleHint?)` | `action_routes.py:113` | 🟡 死代码 |

> 实际项目内的「干预」功能**不走** `submitIntervention`：直接通过管家对话 WS（`user_message` 触发 `INTERVENE` intent）走 `InterventionParser`；Reader.vue 的干预面板用 `setTimeout` 模拟「已记录」动画（见 `api-self-check.md` P1-3）。

---

### 2.5 死代码清单（4 个 API 函数）

| 函数 | 文件:行 | 后端路由 | 状态 |
|---|---|---|---|
| `healthCheck()` | `api/client.ts:30` | `system_routes.py:36` `/api/health` | 全代码库无 import |
| `updateBase()` | `api/projects.ts:69` | `action_routes.py:144` `/api/projects/{id}/base` | 全代码库无 import |
| `submitIntervention()` | `api/actions.ts:11` | `action_routes.py:33` `/api/projects/{id}/interventions` | 全代码库无 import（Reader.vue 58 行的 `submitIntervention` 是**本地函数**） |
| `generateImage()` | `api/actions.ts:36` | `action_routes.py:113` `/api/projects/{id}/image` | 全代码库无 import |

**处理建议**（来自 `api-self-check.md` P2-1）：删除这 4 个函数或在函数体加 `// TODO: v0.6.2 重构清理` 注释。`actions.ts:1-7` 头注释里写了「v0.6.2 刪除 Onboarding 相关函数」，但 actions 残留函数应一起清掉。

---

## 3. WebSocket 通信（核心）

管家对话是 v0.6 起的核心交互入口：用户在 Home/Chat 页与管家 Agent 实时对话，管家按 `intent` 路由到不同下游（CREATE_PROJECT / GENERATE / INTERVENE / LIST_PROJECTS …），全流程走 WS 流式推送 ReAct loop。

> HTTP 部分只覆盖同步短操作（CRUD、单次章节生成）；**管家对话、意图路由、下游 Agent 协调 → 一律 WS**。

### 3.1 端点与连接

```ts
// composables/useStewardChat.ts:13
const WS_BASE = `ws://${window.location.host}/api/chat`
```

- 由 Vite dev server 的 `proxy['/api'].ws = true`（`vite.config.ts:28`）转发到 `http://127.0.0.1:7778/api/chat`
- 生产部署走 Nginx 反代时需透传 `Upgrade` / `Connection: upgrade` 头
- **user_id 写死为 `"anonymous"`**（`ws_manager.py:121`）— v0.4 阶段单机单用户，多用户扩展是后续工作

### 3.2 暴露的状态（ref）

文件：`composables/useStewardChat.ts:32-41`

| 字段 | 类型 | 说明 |
|---|---|---|
| `ws` | `Ref<WebSocket \| null>` | 当前 WS 实例（用于判断是否是「最新 socket」） |
| `connected` | `Ref<boolean>` | `onopen` 触发 true，`onclose` 触发 false |
| `connecting` | `Ref<boolean>` | 调 `connect()` 后立即 true，`onopen` / `onerror` 后 false |
| `messages` | `Ref<StewardMessage[]>` | 消息列表（含 user / agent / tool / system 4 种 role） |
| `thinking` | `Ref<boolean>` | Agent 是否在思考（`agent_thinking` 期间 true，`agent_message` / `error` / `interrupted` 触发 false） |
| `error` | `Ref<string \| null>` | 错误文案（WS 连接错误 / 服务端 `error.message`） |
| `intent` | `Ref<string \| null>` | 最近一次 `agent_message` 的 `intent` 字段 |
| `structuredData` | `Ref<Record<string, any> \| null>` | 最近一次 `agent_message` 的 `structured_data`（项目列表/跳转 URL/确认卡片等） |
| `requireConfirm` | `Ref<boolean>` | `confirm_required` 事件触发 true，用户确认后 false |

### 3.3 暴露的方法

| 方法 | 签名 | 行为 |
|---|---|---|
| `connect()` | `() => void` | 建立 WS 连接；已连接则 no-op；`onopen` → `connected=true`；`onclose` → 清 `ws` ref |
| `send(content, projectId?)` | `(string, string?) => void` | 追加 user 消息到 `messages`，发送 `{ type: "user_message", content, project_id }`；未连接时 `error.value = "WebSocket 未连接"` |
| `sendConfirm(action, confirmed)` | `(string, boolean) => void` | 发送 `{ type: "confirm", action, confirmed }`；`confirmed=true` 时把 `requireConfirm` 置 false |
| `close()` | `() => void` | 主动关 WS + 清 ref |
| `setOnAgentMessage(fn)` / `setOnConfirmRequired(fn)` | `((msg) => void) \| null => void` | 注册回调（用于 ChatBox.vue 监听 `jump_url` 跳转） |

`onUnmounted(() => close())`（`useStewardChat.ts:196-198`）— 组件卸载时自动关连接，**不会泄漏**。

### 3.4 StewardMessage 类型

```ts
// composables/useStewardChat.ts:15-29
interface StewardMessage {
  role: 'agent' | 'user' | 'system' | 'tool'
  content: string
  toolName?: string                              // role=tool 时：工具名
  toolArgs?: Record<string, any>                 // role=tool 时：调用参数
  toolResult?: any                               // role=tool 时：返回结果
  thinking?: boolean                             // role=agent 时：是否 thinking 流（临时占位）
  timestamp: number
  structuredData?: Record<string, any>           // role=agent 时：后端 structured_data
}
```

### 3.5 事件处理逻辑（按服务端事件类型）

文件：`composables/useStewardChat.ts:97-150` 的 `handleEvent(msg)` 函数。

#### `agent_thinking` — LLM 思考中

```ts
// L99-101
if (t === 'agent_thinking') {
  thinking.value = true
  addAgentMessage(msg.content || '思考中...', true)  // isThinking=true
}
```

服务端 `ws_manager.py:173-176` 在调 `NovelSteward.receive()` 之前推一条 `agent_thinking` 作为开场；后续 ReAct loop 里 `_push_agent_trace()`（`ws_manager.py:228-237`）在有 `iterations > 0` 时也会推一条 `agent_thinking`。前端表现为**持续追加 thinking 占位**——`agent_message` 到达时再合并（见下）。

#### `tool_calling` / `tool_result` — 工具调用过程

```ts
// L109-110
} else if (t === 'tool_calling' || t === 'tool_result') {
  // 前端不展示 tool 调用信息，静默忽略
}
```

**前端选择不展示**：避免 ReAct 过程刷屏干扰用户。工具调用细节存在 `structured_data.tool_calls_trace` 里，可由后端调试用，但不在消息流里渲染。

#### `agent_message` — 管家最终回复

```ts
// L111-134
} else if (t === 'agent_message') {
  thinking.value = false
  intent.value = msg.intent || null
  structuredData.value = msg.structured_data || null
  // 替换最后一条 thinking 消息为最终消息
  let lastThinkingIdx = -1
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const m = messages.value[i]
    if (m && m.role === 'agent' && m.thinking) {
      lastThinkingIdx = i
      break
    }
  }
  if (lastThinkingIdx >= 0) {
    messages.value[lastThinkingIdx] = {
      role: 'agent',
      content: msg.content || '',
      timestamp: Date.now(),
      structuredData: msg.structured_data,
    }
  } else {
    addAgentMessage(msg.content || '')
  }
  onAgentMessage?.(msg)   // 触发 ChatBox 注册的回调（处理 jump_url）
}
```

**关键交互模式**：从队尾向前找第一条 `thinking=true` 的 agent 消息，**in-place 替换**——保证 UI 上「思考中」→「回复」是同一条气泡，视觉上不堆叠。

#### `confirm_required` — 危险操作需二次确认

```ts
// L137-138
} else if (t === 'confirm_required') {
  requireConfirm.value = true
  onConfirmRequired?.(msg)
}
```

后端 `ws_manager.py:191-196` 在 `result.structured_data.require_confirm=true` 时推此事件。ChatBox 收到后弹确认卡片，用户点确认 → `sendConfirm(action, true)` 发送 `{ type: "confirm" }` 给后端。

> ⚠️ **当前实现不完整**：后端 `ws_manager.py:115-118` 对 `confirm` 消息**只 echo 了一个 `agent_message`**，未真正处理 action。`api-self-check.md` 「建议 1」列为待实现项。

#### `error` — 服务端错误

```ts
// L140-143
} else if (t === 'error') {
  thinking.value = false
  error.value = msg.message || '未知错误'
  addAgentMessage(`❌ 错误：${msg.message || '未知错误'}`)
}
```

后端错误码（`ws_manager.py:144-150`）：

| code | 触发场景 |
|---|---|
| `TASK_BUSY` | 已有任务在跑（`has_active_task`） |
| `INVALID_MESSAGE_TYPE` | `data.type` 不在白名单 |
| `HANDLER_ERROR` | `handle_user_message` 抛异常（`ws_manager.py:226-230`） |
| `WEBSOCKET_ERROR` | 异常断连兜底（`ws_manager.py:135-141`） |

前端只读 `message` 字段，`code` 不用（`api-self-check.md`「WS 事件对齐」段）。

#### `interrupted` — 用户主动中断

```ts
// L144-146
} else if (t === 'interrupted') {
  thinking.value = false
  addAgentMessage(`⏸️ ${msg.message || '已中断'}`)
}
```

后端 `ws_manager.py:106-113` 在收到 `interrupt` 消息时取消当前任务后推送。当前前端**没有**发送 `interrupt` 的方法（`useStewardChat.ts` 缺 `sendInterrupt()`）— 见 `api-self-check.md` P2-2。

#### `pong` — 心跳响应

```ts
// L147-149
} else if (t === 'pong') {
  // 心跳响应，忽略
}
```

后端 `ws_manager.py:120-122` 在收到 `ping` 时回 `pong`。**前端不主动发 `ping`** — 浏览器 WS 自带 keep-alive，短时间内不会断连。如果将来要做长任务保活，需补 `setInterval(() => ws.value?.send(JSON.stringify({ type: "ping" })), 30000)`。

#### 未知事件

```ts
// L150-152
} else {
  console.debug('[StewardChat] 未知事件:', t, msg)
}
```

**故意保留** — 监控 v0.6.2 后已不发的 `onboarding_*` 3 个事件（`schemas/events.py:51-77`），以及未来新增事件类型的回归。

### 3.6 客户端 → 服务端消息格式

| `type` | 字段 | 触发场景 | 后端处理 |
|---|---|---|---|
| `user_message` | `content: string, project_id?: string, in_onboarding?: boolean` | 用户在 ChatBox 输入 | `ws_manager.py:99-114` → 创建 asyncio task → `handle_user_message` → 调 `NovelSteward.receive()` → 流式推 ReAct 过程 → 推 `agent_message` |
| `confirm` | `action: string, confirmed: boolean` | 危险操作二次确认 | `ws_manager.py:115-118` → **当前仅 echo** `agent_message`（未真处理） |
| `interrupt` | — | 中断当前任务 | `ws_manager.py:106-113` → `ws_manager.interrupt(user_id)` → 取消 task → 推 `interrupted` |
| `ping` | — | 心跳 | `ws_manager.py:120-122` → 回 `pong` |

### 3.7 连接生命周期

```
组件 mount
  └─ ChatBox.vue 调 useStewardChat().connect()
      └─ new WebSocket(WS_BASE)
          ├─ onopen   → connected=true, connecting=false
          ├─ onmessage→ handleEvent(msg)  ← 全部 7 种事件在这里分派
          ├─ onclose  → connected=false, ws=null
          └─ onerror  → error='WebSocket 连接错误', connecting=false

用户输入
  └─ chat.send(content, projectId?)
      └─ addUserMessage() + ws.send({ type: "user_message", content, project_id })

组件 unmount
  └─ useStewardChat.onUnmounted → close()  ← 不会泄漏
```

**重连策略**：当前**不自动重连**。`onclose` 后 `ws=null`，需要业务层（如 ChatBox）决定是否重连（v0.9.6 现状：未做）。若要做，建议加 `watch(connected, ...)` 监听 + 退避重试。

---

## 4. API 自检结论摘要

完整自检报告见 `docs/frontend/api-self-check.md`（由另一位 Agent 编写，2026-07-02 / e717e5b）。

### 4.1 P1（接口契约不一致，3 处）

| ID | 问题 | 位置 |
|---|---|---|
| **P1-1** | 前端发 `actor_feedback` / `actor_character`，后端 Pydantic 默认忽略（v003 删字段后未清理前端） | `api/actions.ts:19-20`、`api/chapters.ts:46-50` |
| **P1-2** | `current_pov*` 3 字段前端声明、后端 `ProjectDetailResponse` 不返回（被 response_model 截断） | `api/projects.ts:32-34` |
| **P1-3** | Reader.vue「干预提交」按钮只 `setTimeout` 弹动画，未真调 `api.submitIntervention`（实际靠 `generateChapter` 的 intervention 透传） | `views/Reader.vue:58-62, 207, 213, 240` |

### 4.2 P2（死代码 / 风格建议）

| ID | 问题 | 位置 |
|---|---|---|
| **P2-1** | 4 个未使用的 API 函数 | `healthCheck` / `updateBase` / `submitIntervention` / `generateImage` |
| **P2-2** | 前端无 WS `interrupt` / `ping` 发送 | `useStewardChat.ts` 缺 `sendInterrupt()` |
| **P2-3** | 后端 `/api/info` 端点无前端调用 | `system_routes.py:48` |
| **P2-4** | list 端点 `palette` 始终为 `""` | `services/project_manager.py:148` 硬编码 |
| **P2-5** | `ChapterInfo` list 不返回 `word_count` / `file_path` | `chapter_routes.py:65-72` |

### 4.3 整体健康度

🟢 **HTTP 调用层 100% 对齐**（无 422 / 解析失败风险）。P1-1 / P1-2 应在下版本前清理，其余为改进项。
