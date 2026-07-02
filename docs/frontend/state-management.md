# Frontend 状态管理

> 元信息：生成日期 2026-07-02 · 版本 v0.9.6 · commit e717e5b

本文档梳理 realtime-novel 前端的 Pinia 状态管理设计：3 个 store + 1 个 composable，覆盖项目管理、章节内容、全局对话（WebSocket 流式）、通用管家对话四个核心数据域。

---

## 1. Pinia 状态管理概览

realtime-novel 前端使用 Pinia（Setup 语法）管理状态，外加 1 个 Vue 3 composable 处理管家 WS。共 4 个状态单元：

| 单元 | 类型 | 路径 | 职责 |
|------|------|------|------|
| `useProjectsStore` | Pinia store | `frontend/src/stores/projects.ts` | 项目列表、详情、CRUD、探索度切换 |
| `useChaptersStore` | Pinia store | `frontend/src/stores/chapters.ts` | 章节列表、当前章节内容、生成、summary 缓存 |
| `useConversationStore` | Pinia store | `frontend/src/stores/conversation.ts` | 一对一 active 对话（HTTP+WS 流式） |
| `useStewardChat` | composable | `frontend/src/composables/useStewardChat.ts` | 通用管家对话（WS，多 intent） |

### 协作关系图

```
            ┌─────────────────────────────────────────┐
            │            Vue Components               │
            └────┬───────────────┬────────────┬───────┘
                 │               │            │
        ┌────────▼──────┐ ┌─────▼──────┐ ┌───▼────────────┐
        │ useProjects   │ │ useChapters│ │ useConversation│
        │ Store         │ │ Store      │ │ Store          │
        │ (HTTP)        │ │ (HTTP)     │ │ (WS 流式)      │
        └───────────────┘ └────────────┘ └────────────────┘
                                                       │
                                                       │ 共用 WS_BASE
                                                       │ (/api/chat)
                                                       ▼
                                            ┌────────────────────┐
                                            │ useStewardChat     │
                                            │ (composable, WS)   │
                                            │ 通用管家，多 intent │
                                            └────────────────────┘
```

关键约定：

- `useConversationStore` 和 `useStewardChat` 都连同一个 WS 端点 `ws://<host>/api/chat`，但面向不同业务场景（前者用于小说正文流式生成，后者用于管家多意图对话）。
- 两个 WS 状态单元互不感知；UI 层按场景选择使用哪一个。
- HTTP 层的 store 走 `import * as api from '@/api/<module>'`，异常统一写到 `error` ref。

---

## 2. `stores/projects.ts`

封装项目域的 HTTP 状态：列表、详情、创建、删除、探索度切换。

### state 字段表

| 字段 | 类型 | 默认值 | 说明 | 行号 |
|------|------|--------|------|------|
| `projects` | `Ref<api.ProjectInfo[]>` | `[]` | 项目列表（轻量信息） | 9 |
| `total` | `Ref<number>` | `0` | 后端返回的总数 | 10 |
| `current` | `Ref<api.ProjectDetail \| null>` | `null` | 当前选中的项目详情 | 11 |
| `loading` | `Ref<boolean>` | `false` | 列表/详情加载态 | 12 |
| `error` | `Ref<string \| null>` | `null` | 最近一次错误信息 | 13 |
| `hasCurrent` | `ComputedRef<boolean>` | — | `current.value !== null` 的派生值 | 67 |

### action 方法表

| 方法 | 参数 | 返回 | 说明 | 行号 |
|------|------|------|------|------|
| `loadList` | `limit?: number`（默认 50） | `Promise<void>` | 拉取项目列表，写入 `projects` / `total` | 15 |
| `loadOne` | `id: string` | `Promise<void>` | 拉取单个项目详情到 `current` | 27 |
| `create` | `name: string`, `initialPrompt?: string` | `Promise<api.CreateProjectResponse>` | 新建项目后自动 `loadList` 刷新 | 39 |
| `remove` | `id: string` | `Promise<api.DeleteProjectResponse>` | 乐观本地过滤 + 后台再 `loadList` 一次 | 46 |
| `updateExplorationLevel` | `id: string`, `level: 'conservative' \| 'standard' \| 'wild'` | `Promise<api.UpdateExplorationResponse>` | v0.8 探索度切换：先 `loadOne(id)` 刷新详情，再 `loadList` 刷新列表 | 55 |

注意点：

- `remove`（`stores/projects.ts:46`）采用乐观更新：先本地 `filter` 掉条目、`total - 1`，再后台 `await loadList()` 同步权威数据。
- `create` 不在本地 push 新条目，而是直接 `loadList`，避免与后端排序/筛选冲突。
- `loadList` / `loadOne` 各自在 `try/catch/finally` 中维护 `loading` 与 `error`，符合全局异常写入约定。

---

## 3. `stores/chapters.ts`

封装章节域：列表、当前章节正文、生成触发、summary 缓存。

### state 字段表

| 字段 | 类型 | 默认值 | 说明 | 行号 |
|------|------|--------|------|------|
| `list` | `Ref<api.ChapterListItem[]>` | `[]` | 章节列表（含 num / title / summary） | 9 |
| `current` | `Ref<api.ChapterContent \| null>` | `null` | 当前章节正文 | 10 |
| `currentSummary` | `Ref<string \| null>` | `null` | 当前章节的 1 句 summary（v0.5） | 12 |
| `loading` | `Ref<boolean>` | `false` | 列表/详情加载态 | 13 |
| `generating` | `Ref<boolean>` | `false` | LLM 生成中标志（与 `loading` 区分） | 14 |
| `error` | `Ref<string \| null>` | `null` | 最近一次错误信息 | 15 |
| `count` | `ComputedRef<number>` | — | `list.length` | 60 |
| `latest` | `ComputedRef<api.ChapterListItem \| null>` | — | `list[0]`，最近生成的章节 | 61 |

### action 方法表

| 方法 | 参数 | 返回 | 说明 | 行号 |
|------|------|------|------|------|
| `loadList` | `projectId: string` | `Promise<void>` | 拉取某项目的章节列表 | 17 |
| `loadOne` | `projectId: string`, `n: number` | `Promise<void>` | 拉取第 n 章正文，并从 `list` 同步 `currentSummary` | 29 |
| `generate` | `projectId: string`, `options?: { intervention?, actor_feedback?, actor_character? }` | `Promise<api.GenerateChapterResponse>` | 触发 LLM 生成新章节；成功后刷新列表 + 加载新章节正文 | 43 |

注意点：

- `generate`（`stores/chapters.ts:43`）维护独立的 `generating` 标志，避免与列表 `loading` 互踩；调用方可同时按 `generating` 渲染"生成中"UI。
- `loadOne` 会从 `list` 里用 `find(c => c.num === n)` 同步 summary（`stores/chapters.ts:36`），保证后端省略 summary 时前端也有兜底。
- `generate` 在 `catch` 中 `throw e`（`stores/chapters.ts:55`），把异常透传给调用方做 toast。

---

## 4. `stores/conversation.ts`

v0.5 设计：每个 user 只有 1 个 active conv，**"新建对话" = 关闭旧 WS + 重连（后端创建新 conv）**。

### state 字段表

| 字段 | 类型 | 默认值 | 说明 | 行号 |
|------|------|--------|------|------|
| `activeConvId` | `Ref<string \| null>` | `null` | 当前 active 对话 ID | 14 |
| `status` | `Ref<'active' \| 'invalidated' \| 'archived' \| 'none'>` | `'none'` | 对话生命周期状态 | 15 |
| `ws` | `Ref<WebSocket \| null>` | `null` | WS 实例引用 | 16 |
| `messages` | `Ref<Array<{ role, content, tool_calls? }>>` | `[]` | 对话消息流水 | 17 |
| `connected` | `Ref<boolean>` | `false` | WS 连接状态 | 18 |
| `streaming` | `Ref<boolean>` | `false` | assistant_chunk 流式追加中 | 19 |
| `error` | `Ref<string \| null>` | `null` | 最近错误 | 96 |
| `isStreaming` | `ComputedRef<boolean>` | — | `streaming.value` 派生 | 97 |
| `hasMessages` | `ComputedRef<boolean>` | — | `messages.length > 0` 派生 | 98 |

> 注意 `error` 在文件中位置较靠后（`stores/conversation.ts:96`）但功能与其他 store 一致。

### action 方法表

| 方法 | 参数 | 返回 | 说明 | 行号 |
|------|------|------|------|------|
| `connect` | — | `void` | 建立 WS，绑定 onopen/onmessage/onclose/onerror；处理 `conversation_started` / `_invalidated` / `assistant_chunk` / `assistant_done` / `tool_call` / `error` 事件 | 21 |
| `sendUserMessage` | `content: string`, `projectId?: string` | `void` | 推送 user 消息到本地 + 通过 WS 发送；要求 WS OPEN | 76 |
| `newConversation` | — | `void` | 关闭旧 WS、清空状态、重连（后端创建新 conv） | 90 |
| `disconnect` | — | `void` | 关闭 WS、清空引用 | 101 |

事件分支处理（`stores/conversation.ts:32-66`）：

| 服务端 `type` | 行为 |
|---------------|------|
| `conversation_started` | 写 `activeConvId` + `status='active'` |
| `conversation_invalidated` | `status='invalidated'` |
| `assistant_chunk` | `streaming=true`；若末尾是 assistant 消息则 `content += msg.delta`，否则 push 新 assistant 消息 |
| `assistant_done` | `streaming=false` |
| `tool_call` | push 一条 `role: 'tool'` 消息，带 `tool_calls` |
| `error` | 写 `error` + `streaming=false` |

注意 `sendUserMessage` 把 `conversation_id` 一并发出（`stores/conversation.ts:86`），但 v0.5 后端会忽略/覆盖，由服务端单点维护 active conv。

---

## 5. `composables/useStewardChat.ts`（WS 状态管理，重点）

通用管家对话 composable（v0.6 引入），与 onboarding chat 的关键区别：**不绑定 step、支持所有 intent、处理 agent_message + structured_data + confirm_required 事件**。

> 与 `useConversationStore` 的关键差异：管家 WS 面向"管家"语义（多意图：CREATE_PROJECT / GENERATE / INTERVENE / LIST_PROJECTS / ...），而 conversation store 面向"小说正文流式生成"。

### 暴露的 ref 状态

| 字段 | 类型 | 默认值 | 说明 | 行号 |
|------|------|--------|------|------|
| `ws` | `Ref<WebSocket \| null>` | `null` | WS 实例引用 | 21 |
| `connected` | `Ref<boolean>` | `false` | 已连接 | 22 |
| `connecting` | `Ref<boolean>` | `false` | 连接中（onopen 之前） | 23 |
| `messages` | `Ref<StewardMessage[]>` | `[]` | 完整消息流水（含 agent/user/system/tool） | 24 |
| `thinking` | `Ref<boolean>` | `false` | LLM 思考中（agent_thinking 事件） | 25 |
| `error` | `Ref<string \| null>` | `null` | 最近错误 | 26 |
| `intent` | `Ref<string \| null>` | `null` | 后端返回的当前 intent（如 `CREATE_PROJECT`） | 27 |
| `structuredData` | `Ref<Record<string, any> \| null>` | `null` | 当前消息携带的结构化数据（项目列表 / 跳转 URL / 确认卡片等） | 28 |
| `requireConfirm` | `Ref<boolean>` | `false` | 是否需要前端确认（confirm_required 事件） | 29 |

### 暴露的方法

| 方法 | 参数 | 返回 | 说明 | 行号 |
|------|------|------|------|------|
| `connect` | — | `void` | 打开 WS；onopen → `connected=true` + `connecting=false`；所有回调内做 `ws.value === socket` 守护避免僵尸连接串扰 | 51 |
| `send` | `content: string`, `projectId?: string \| null` | `void` | 推 user 消息到本地 + WS 发送 `user_message` | 155 |
| `sendConfirm` | `action: string`, `confirmed: boolean` | `void` | 发送 `confirm` 事件；`confirmed=true` 时清 `requireConfirm` | 167 |
| `close` | — | `void` | 主动关闭 WS | 177 |
| `setOnAgentMessage` | `fn: ((msg) => void) \| null` | `void` | 注册 / 覆盖 `agent_message` 回调（用于跳转、埋点等） | 185 |
| `setOnConfirmRequired` | `fn: ((msg) => void) \| null` | `void` | 注册 / 覆盖 `confirm_required` 回调 | 186 |

另外内部还实现了 `addAgentMessage` / `addUserMessage` / `addToolMessage` 三个 helper（`useStewardChat.ts:31-49`），分别构造对应角色的 `StewardMessage`，但未对外暴露。

### `StewardMessage` 类型定义

```ts
// useStewardChat.ts:11-25
export interface StewardMessage {
  role: 'agent' | 'user' | 'system' | 'tool'
  content: string
  /** tool 调用详情（role=tool 时） */
  toolName?: string
  toolArgs?: Record<string, any>
  toolResult?: any
  /** thinking 流（LLM 思考中） */
  thinking?: boolean
  timestamp: number
  /** 后端 structured_data（项目列表/跳转 URL/确认卡片等） */
  structuredData?: Record<string, any>
}
```

### 事件处理逻辑（按 `msg.type` 分支）

入口：`handleEvent(msg)`（`useStewardChat.ts:78`）。所有分支会先做 `if (ws.value !== socket) return` 守护（`useStewardChat.ts:60`），避免关闭后旧 socket 的延迟事件污染状态。

| `msg.type` | 行为 | 行号 |
|------------|------|------|
| `agent_thinking` | `thinking=true`；`addAgentMessage(content, true)`（标记为 thinking 占位） | 80 |
| `tool_calling` / `tool_result` | 静默忽略，不在前端展示 tool 调用 | 83 |
| `agent_message` | `thinking=false`；写入 `intent` + `structuredData`；**查找最后一条 thinking 消息并替换**为最终内容（`useStewardChat.ts:96-109`），找不到则 `addAgentMessage`；最后触发 `onAgentMessage?.(msg)` | 85 |
| `confirm_required` | `requireConfirm=true`；触发 `onConfirmRequired?.(msg)` | 111 |
| `error` | `thinking=false`；写 `error`；追加一条 `❌ 错误：...` agent 消息 | 114 |
| `interrupted` | `thinking=false`；追加一条 `⏸️ ...` agent 消息 | 118 |
| `pong` | 心跳响应，忽略 | 121 |
| 其它 | `console.debug` 记录未知事件 | 123 |

`agent_message` 分支的"替换最后一条 thinking 消息"是管家聊天的关键 UX 模式：先 emit `agent_thinking` 占位、LLM 推理完成后再 emit `agent_message` 时把它"打补丁"成最终文本，避免前端看到一条 thinking 又多一条最终消息的重复气泡。

### 连接生命周期

1. **挂载**：组件 `setup` 中调用 `useStewardChat()` 拿到返回对象；调用 `connect()`（`useStewardChat.ts:51`）打开 WS。
2. **打开**：`onopen` 内做 `ws.value === socket` 守护（`useStewardChat.ts:55`），置 `connected=true`、`connecting=false`。
3. **运行中**：`send` / `sendConfirm` 发送；服务端事件通过 `handleEvent` 分类处理。
4. **关闭/异常**：`onclose` / `onerror` 同样做 `ws.value === socket` 守护，避免与新连接交叉污染；调用 `close()` 主动关闭；`onUnmounted(() => close())`（`useStewardChat.ts:189`）在组件卸载时自动清理。
5. **回调**：`onAgentMessage` / `onConfirmRequired` 是模块级闭包变量（`useStewardChat.ts:182-186`），通过 `setOnAgentMessage` / `setOnConfirmRequired` 注入；UI 可借此做跳转、弹窗、埋点等副作用。

---

## 6. 数据流示例：用户发消息 → 3 store + composable 协作

下面走一条"用户向管家询问项目列表"的典型路径，说明 4 个状态单元的协作。

```
[用户 UI] 项目广场页点击"问问管家"
   │
   ▼
StewardChatPanel.vue  setup()
   │ const steward = useStewardChat()
   │ steward.setOnAgentMessage((msg) => { /* 跳转 / 埋点 */ })
   │ steward.connect()
   │
   ▼
[WS 已连接] steward.connected = true
   │
   ▼
[用户输入] "列出我所有的项目"
   │ steward.send('列出我所有的项目', null)
   │
   ▼
addUserMessage → messages.push({ role: 'user', content: '...' })
   │
   ▼
WS.send({ type: 'user_message', content, project_id: undefined })
   │
   ▼
[后端 Steward Agent] 收到 user_message
   │ 1) emit agent_thinking: "正在查询项目..."
   │ 2) emit tool_calling / tool_result（前端忽略）
   │ 3) emit agent_message: { intent: 'LIST_PROJECTS', content: '已为你找到 N 个项目', structured_data: { projects: [...] } }
   │
   ▼
[前端 handleEvent]
   │ 'agent_thinking' → thinking=true + messages.push({ thinking: true, content: '正在查询项目...' })
   │ 'agent_message'   → thinking=false
   │                    → intent.value = 'LIST_PROJECTS'
   │                    → structuredData.value = { projects: [...] }
   │                    → 替换最后一条 thinking 消息为最终文本
   │                    → onAgentMessage(msg) 触发
   │
   ▼
[UI 响应]
   │ 渲染最终消息气泡
   │ 读取 structuredData.value.projects 渲染"项目卡片列表"
   │ 点击卡片 → router.push('/projects/<id>')  ← 这是 store 之外的副作用
   │
   ▼
[与此同时，projects store 协作]
   │ 用户在管家气泡里点击"跳转到项目"
   │ 路由切到 /projects/<id>
   │ ProjectDetail.vue 调 useProjectsStore.loadOne(id)
   │ → HTTP GET /api/projects/:id
   │ → current.value = detail
   │
   ▼
[用户进入详情页，点"生成下一章"]
   │ ChapterEditor.vue 调 useChaptersStore.generate(projectId, { intervention: '...' })
   │ → generating.value = true
   │ → HTTP POST /api/projects/:id/chapters
   │ → 成功后 loadList + loadOne
   │ → useConversationStore 同步处于"已连接"状态，UI 可在气泡中显示
   │   "下一章生成完成"（管家 WS 推 agent_message 通知）
```

总结：

- 管家 WS（`useStewardChat`）负责"对话语义"，所有跨场景动作（创建/列表/跳转/确认）都通过它驱动。
- 项目 / 章节 store 是数据真相源（source of truth），所有详情都来自 HTTP 拉取。
- `useConversationStore` 与 `useStewardChat` 是两条独立的 WS 流，前者面向"小说正文流式生成"，后者面向"管家多意图对话"；UI 不会同时使用两者。
- 副作用（路由跳转、确认弹窗、埋点）通过 `setOnAgentMessage` / `setOnConfirmRequired` 注入 composable，避免 composable 强耦合到具体路由库。
