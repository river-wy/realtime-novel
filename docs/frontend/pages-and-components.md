# 前端页面与组件文档

> **元信息**
> - 文档日期：2026-07-02
> - 项目版本：v0.9.6（`e717e5b`）
> - 范围：`frontend/src/views/*.vue` + `frontend/src/components/ChatBox.vue` + `frontend/src/composables/useStewardChat.ts` + `frontend/src/router/index.ts`
> - 关联：本文只覆盖**页面级视图**与**可复用 ChatBox 组件**；不细讲 `useStewardChat` 内部 WebSocket 协议（详见 `composables/useStewardChat.ts`）

---

## 1. 路由树

来自 `frontend/src/router/index.ts:6-39`，**实际注册 5 个路由**：

| # | path | name | component | meta.title | 备注 |
|---|------|------|-----------|------------|------|
| 1 | `/` | `home` | `views/Home.vue` | 首页 | 启动页，零交互 |
| 2 | `/chat` | `chat` | `views/Chat.vue` | 管家对话 | 嵌入 `<ChatBox>` |
| 3 | `/reader/:projectId/:chapterNum?` | `reader` | `views/Reader.vue` | 阅读 | `:chapterNum` 可省，默认 1 |
| 4 | `/world/:projectId?` | `world` | `views/World.vue` | 世界 | `:projectId` 可省，默认 demo |
| 5 | `/worlds` | `world-list` | `views/WorldList.vue` | 我的世界 | 项目列表 |

`router/index.ts:40-49`：

- 使用 `createWebHistory()`（无 hash）
- `scrollBehavior` 固定 `top: 0`
- `afterEach` 把 `meta.title` 拼成 `小说 · 世界` 写到 `document.title`

---

## 2. Home.vue — 启动页（少女梦幻风）

> 路径：`frontend/src/views/Home.vue`，614 行，**无业务逻辑**，纯视觉入口。

### 2.1 视觉结构

`Home.vue:42-118`，页面是 `position: fixed` 全屏 `home-launch`，分层（z-index 由下至上）：

1. **deco-bubbles**（`:46-58`）：8 个漂浮气泡，`bubble-float` 关键帧从底部 -20px 升到 -100vh，颜色 `radial-gradient` 樱花粉 30% 透明
2. **deco-curve**（`:60-70`）：顶部 / 底部各一条 SVG 装饰曲线（樱花粉 8% + 紫罗兰 6% 透明）
3. **hero-bg-layer**（`:72-75`）：`@/assets/HOME-主图.png` 铺满，叠加 `.hero-bg-overlay` 渐变
4. **launch-content**（`:90-117`）：中央内容
   - deco-divider（点 + 横线 + sparkle 装饰）
   - `.logo-area`：logo 文字 PNG + 副标题 "让 AI 陪你写一个世界"
   - `.launch-btn`：启动新世界按钮（带 6 个 `particle` 粒子）
   - `.features`：4 个特性卡（AI 共创 / 多世界 / 实时生成 / 探索度调节）

### 2.2 关键交互

| 元素 | 行为 | 文件位置 |
|------|------|----------|
| `.orb-bubble`（右上角 3D orb） | `router.push({ name: 'world-list' })` | `Home.vue:78-88` |
| `.launch-btn`（中央主按钮） | `router.push({ name: 'chat' })` | `Home.vue:104-110` |
| `heroImage` | `import` 自 `@/assets/HOME-主图.png` | `Home.vue:9` |
| `logoImage` | `import` 自 `@/assets/logo文字.png` | `Home.vue:10` |

### 2.3 常量

- `features`（`Home.vue:12-17`）：4 项特性 + phosphor icon 名称
- `floatingBubbles`（`Home.vue:20-29`）：8 个气泡的位置 / 延时 / 时长

> **与 ChatBox 无关**：Home.vue 不直接调用任何 ChatBox。点击启动后跳到 `/chat` 才进入管家对话。

---

## 3. Chat.vue — 管家对话页

> 路径：`frontend/src/views/Chat.vue`，265 行。Home 按下「启动新世界」后落地页。

### 3.1 布局

`Chat.vue:65-112`：

- `header.chat-header`（玻璃毛玻璃 + 渐变 LOGO 文字）：返回按钮 + 标题 + 「我的项目 (N)」按钮
- `main.chat-main`（`max-width: 900px` 居中）：嵌入 `<ChatBox>` 全权负责聊天 UI

### 3.2 项目浮层

`Chat.vue:71-92`：点击 header 右侧「我的项目」按钮弹出 `.project-overlay` 全屏遮罩，渲染最近 7 个项目卡片，点击 → `goToProject(id)` → `router.push(/reader/${id}/1)`。

### 3.3 关键 Props / Events 透传

`Chat.vue:113-118`：

```vue
<ChatBox
  placeholder="和管家聊聊你的小说世界..."
  :welcome-message="`👋 你好！...`"
  @jump="onJump"
  @require-confirm="(action) => console.log('需要确认:', action)"
/>
```

- `onJump(url)`（`Chat.vue:33-35`）：直接 `router.push(url)`，不解析相对/绝对（jump_url 通常是后端给的相对路径如 `/reader/abc/1`）

> 详见第 7 章 ChatBox 完整说明。

---

## 4. World.vue — 项目世界管理页

> 路径：`frontend/src/views/World.vue`，539 行。

### 4.1 布局：封面 banner + 3 栏

`World.vue:80-167`：

#### 4.1.1 顶部 cover-banner

`World.vue:82-105`：

- 高 240px，`.has-image` 用 `cover_image_url` 作背景图，`.placeholder` 用 `--color-bg-surface → --color-bg-elevated` 渐变
- `.cover-overlay`：从 `rgba(10,5,20,0.2)` 顶部到 `rgba(10,5,20,0.85)` 底部的渐变蒙版，保证标题可读
- `.cover-title-area`：项目名 + 三个 badge（调色板 / 探索度 / 章节数）

#### 4.1.2 3 栏 .world-body

`World.vue:107-167` + 样式 `World.vue:288-294`：

```
grid-template-columns: 240px 1fr 240px;
@media (max-width: 1024px) { grid-template-columns: 1fr; }
```

| 栏 | class | 内容 | 动画 |
|----|-------|------|------|
| 左 | `.info-panel` | dl 信息表（章节数/调色板/探索度/状态）+ 「进入阅读」按钮 | `fadeInLeft 100ms` |
| 中 | `.chapters-panel` | `.chapter-list` 章节行 + `.ch-arrow` 右箭头 | `fadeInUp 200ms` |
| 右 | `.ops-panel` | 回档输入 + 删除按钮，**`position: sticky; top: 80px`** | `fadeInRight 300ms` |

`.ops-panel` 边框用 `rgba(251,191,36,0.25)` 警示色（`World.vue:269`）。

### 4.2 关键功能

| 功能 | 触发 | 行为 | 行号 |
|------|------|------|------|
| 加载 | `onMounted(load)` | `loadOne(projectId)` + `chaptersStore.loadList(projectId)` | `World.vue:24-28, 62` |
| 进入章节 | 点击 `.chapter-row` | `router.push({ name: 'reader', params: { projectId, chapterNum: n } })` | `World.vue:60-62, 145-155` |
| 回档 | `.btn-rollback` | `rollbackProject(projectId, rollbackTo)` → 成功后 `load()` 重拉 | `World.vue:18-30, 159-164` |
| 删除项目 | `.btn-delete` | `confirm()` 二次确认 → `projectsStore.remove()` → `router.push('/')` | `World.vue:32-43, 167` |
| 无章节 hint | `chaptersStore.count === 0` | 显示「请回首页对话中说『生成第 1 章』」 | `World.vue:127` |

### 4.3 计算属性

`World.vue:14`：

```ts
const projectId = computed(() => route.params.projectId as string || 'demo-urban-romance')
```

> `:projectId` 可省，路由 `props: true`（`router/index.ts:24`）。

---

## 5. Reader.vue — 章节阅读页

> 路径：`frontend/src/views/Reader.vue`，932 行。**3 个浮层 + 1 个固定栏**叠加，body 是 2 栏网格。

### 5.1 整体布局

| 层 | 元素 | 文件位置 |
|----|------|----------|
| 1 | `.reader-header` 顶部条 | `Reader.vue:65-104` |
| 2 | `.reader-body` 2 栏 | `Reader.vue:106-180` |
| 3 | `.intervention-bar` 底部固定 | `Reader.vue:184-249` |
| 4 | `.drawer` 章节侧滑浮层 | `Reader.vue:254-274` |

### 5.2 顶部 .reader-header

`Reader.vue:65-104` + 样式 `Reader.vue:308-365`：

- `.header-bg`：若有 `cover_image_url` 作 blurred (`blur(8px) scale(1.1)`) 背景
- `.header-overlay`：`rgba(10,5,20,0.6)` 半透明蒙版
- `.header-content`（flex 横向）：
  - 返回按钮 → `router.push({ name: 'world', params: { projectId } })`
  - `.reader-title` 项目名（`text-overflow: ellipsis`）
  - **`.exploration-toggle` 探索度滑钮**（保守/标准/狂野），`toggle-slider` 滑块按 `:data-level` 用 `transform: translateX(0/100/200%)` 移动，`transition 300ms`（`Reader.vue:95-101`，样式 `Reader.vue:392-425`）
  - `.header-btn-wide` 「章节」按钮 → 切换 `showDrawer`

> **不是 Bento 布局**：body 是 `grid-template-columns: 200px 1fr`（`Reader.vue:428-433`），左栏 `.left-col` 是玻璃面板 sticky，右栏 `.center-col` 是正文流。

### 5.3 左栏 .left-col（玻璃面板）

`Reader.vue:108-160` + 样式 `Reader.vue:437-499`：

- `.cover-thumb` 1:1 缩略图（无封面时显示 `ph-book-open` 占位）
- `.nav-btn` 上一章 / 下一章（`chapterNum <= 1` 时禁用）
- `.progress-bar` + `.progress-fill` 进度条，`width = chapterNum / max(count, 1) * 100%`
- `.progress-text`「第 N / M 章」+ `.btn-generate`「生成下一章」（生成中显示 `.spinner`）

`.left-col` 自身 `position: sticky; top: var(--space-4)`（`Reader.vue:443-444`）。

### 5.4 中栏 .center-col

`Reader.vue:163-180`：

- `chaptersStore.loading` 渲染骨架屏（8 条 `.skeleton-line`，`shimmer` 1.8s 循环，`Reader.vue:166-176`）
- 否则渲染：
  - `.summary-pill` 概要胶囊（仅在 `chaptersStore.currentSummary` 存在时）
  - `<h1 class="chapter-title">` 标题
  - `.chapter-meta` 字数 + 生成日期
  - `.prose pre` 正文（`max-width: 68ch; line-height: 1.9`）
  - `.chapter-tail` 章尾标记「— 第 N 章 完 —」

### 5.5 底部 .intervention-bar（作者干预）

`Reader.vue:184-249` + 样式 `Reader.vue:608-...`：

- `position: fixed; bottom: 0`；`max-width: 1280px; margin: 0 auto` 居中
- **折叠态**（`.bar-collapsed`，`Reader.vue:188-204`）：icon + 单行 input + 提交 + 展开按钮
- **展开态**（`.bar-expanded`，`Reader.vue:206-248`）：标题 + 折叠按钮 + 4 行 textarea + 提交 + 反馈提示 + hint
- 切换用 `transition name="bar-swap" mode="out-in"`
- 提交成功 `.record-feedback = true` 显示 2 秒 ✓ 反馈（`Reader.vue:54-57`）

### 5.6 章节 Drawer

`Reader.vue:254-274` + 样式 `Reader.vue:833-900`：

- `position: fixed; right: 0; width: 360px; backdrop-filter: blur(20px)`
- `transition name="slide"` 滑入
- 列出 `chaptersStore.list` 所有章节，当前章节加 `.active` 高亮
- 点击 → `goToChapter(n)` + `showDrawer = false`

### 5.7 响应式断点

| 断点 | 行为 | 文件位置 |
|------|------|----------|
| `≤ 1024px` | `.reader-body` 变单列；`.left-col` 改横向 flex，缩略图 64×64 | `Reader.vue:917-924` |
| `≤ 640px` | `.header-content` wrap；标题下移；正文降字号 | `Reader.vue:925-930` |
| `prefers-reduced-motion` | 关闭所有动画 | `Reader.vue:911-916` |

### 5.8 关键状态

`Reader.vue:18-22`：

```ts
const projectId = computed(() => route.params.projectId as string)
const chapterNum = computed(() => parseInt(route.params.chapterNum as string) || 1)
const intervention = ref('')
const showDrawer = ref(false)
const interventionExpanded = ref(false)
const recordFeedback = ref(false)
```

`watch(() => route.params, loadAll)`（`Reader.vue:64`）：路由参数变化时重新加载章节。

---

## 6. WorldList.vue — 项目列表页

> 路径：`frontend/src/views/WorldList.vue`，480 行。

### 6.1 布局

`WorldList.vue:87-176`：

- `header.list-header`：返回按钮 + `<h1>我的世界</h1>` + `.count` 圆形徽标
- 三种状态：
  1. `projectsStore.loading` → `.skeleton-grid` 3 个骨架卡（`WorldList.vue:91-107`）
  2. `projects.length === 0` → `.empty` 空状态 + 「去首页对话启动」按钮（`WorldList.vue:109-115`）
  3. 正常 → `.project-grid`（`grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))`）项目卡

### 6.2 项目卡片

`WorldList.vue:118-167`：

- `.card-thumb`：有封面用 `cover_image_url` 背景图，无则显示 `ph-book-open` 占位
- `.card-content`：
  - `.card-title` 项目名
  - `.card-meta`：调色板 + 探索度 badge（`exploration-{level}`）+ 状态 badge（`status-{status}`）
  - `.card-chapter-count` 章节数
- `.card-actions`：查看 / 立即阅读（无章节时禁用）
- `.card-menu`（右上角 `ph-dots-three-vertical`）→ `.card-menu-dropdown` 删除项

### 6.3 关键行为

| 触发 | 行为 | 行号 |
|------|------|------|
| 卡片点击 | `chapter_count > 0 ? goToReader(p) : goToWorld(p)` | `WorldList.vue:121, 27-35` |
| 查看按钮 | `goToWorld(p)` → `/world/:id` | `WorldList.vue:158-160, 29-31` |
| 立即阅读 | `goToReader(p)` → `/reader/:id/1` | `WorldList.vue:163-166, 27-28` |
| 三点菜单 | `toggleMenu($event, id)` 切换 `openMenuId` | `WorldList.vue:38-41, 167-175` |
| 删除 | `confirm()` 二次确认 → `projectsStore.remove(id)` | `WorldList.vue:48-58` |
| 点击外部关闭菜单 | `document.addEventListener('click', onDocClick)` | `WorldList.vue:60-62` |

### 6.4 辅助函数

`WorldList.vue:66-80`：

- `explorationIcon(level)` → `{ conservative: 'shield', standard: 'scales', wild: 'planet' }`
- `explorationLabel(level)` → `{ conservative: '保守', standard: '标准', wild: '狂野' }`
- `statusIcon(status)` / `statusLabel(status)` → `circle / circle-half / check-circle` + `未启动 / 进行中 / 已完成`

---

## 7. ChatBox.vue — 通用管家对话组件（**重点**）

> 路径：`frontend/src/components/ChatBox.vue`，388 行。**前端不展示 tool_call / tool_result 消息**（注释见 `ChatBox.vue:3`）。

### 7.1 Props

`ChatBox.vue:10-17`：

| Prop | 类型 | 默认值 | 含义 |
|------|------|--------|------|
| `placeholder` | `string` | `'和管家聊聊你的小说...'` | textarea 占位文字 |
| `projectId` | `string \| null` | `null` | 透传给后端，标识当前会话所属项目 |
| `welcomeMessage` | `string` | `'你好！我是你的小说管家。\n\n...'` | 首次挂载时插入的管家欢迎消息 |

### 7.2 Emits

`ChatBox.vue:22-25`：

| Event | Payload | 触发条件 |
|-------|---------|----------|
| `jump` | `url: string` | 后端 `agent_message` 携带 `structured_data.jump_url` **或** 用户点击项目卡片 / 候选项目 |
| `require-confirm` | `action: string, details: any` | 后端 `confirm_required` 事件 |

> ChatBox **不会自动跳转**到 `jump_url`，而是通过 emit 把决策权交给父组件（Chat.vue 的 `onJump` 用 `router.push(url)` 跳）。

### 7.3 内部状态机

`ChatBox.vue:27-29`：

```ts
const chat = useStewardChat()        // 拿 WS + messages + thinking + error
const inputText = ref('')             // textarea 双向绑定
const chatContainer = ref<HTMLElement | null>(null)  // 滚动容器
```

`useStewardChat.ts:8` 暴露 `StewardMessage` 接口（`role: agent | user | system | tool`），完整状态字段在 `useStewardChat.ts:16-40`。

**生命周期**：

| 阶段 | 行为 | 行号 |
|------|------|------|
| `onMounted` | `chat.connect()` 打开 WebSocket；如果 `welcomeMessage` 非空且 `messages.value.length === 0`，push 一条 agent 欢迎消息 | `ChatBox.vue:40-48` |
| 收到 `agent_message` | `useStewardChat.ts:117-138` 替换最后一条 `thinking` 消息为最终消息，并调用 `onAgentMessage` 回调 | — |
| 收到 `confirm_required` | 设置 `requireConfirm = true`，调用 `onConfirmRequired` 回调 → ChatBox emit `require-confirm` | `useStewardChat.ts:140-144, ChatBox.vue:35-38` |
| 收到 `agent_thinking` | push 一条 `thinking: true` 的 agent 消息，光标 `▋` 闪烁 | `useStewardChat.ts:104-108, ChatBox.vue:103-108` |
| `watch messages.length` | 滚动到底部 `behavior: 'smooth'` | `ChatBox.vue:51-55` |

**事件类型与渲染**（`useStewardChat.ts:97-156`）：

| 后端事件 | ChatBox 行为 |
|----------|--------------|
| `agent_thinking` | push 一条 `agent + thinking: true` 消息（带闪烁光标） |
| `tool_calling` / `tool_result` | **静默忽略**（前端不展示 TOOL 调用） |
| `agent_message` | 替换最后一条 thinking；触发 `onAgentMessage` 回调；ChatBox 用回调 emit `jump` |
| `confirm_required` | `requireConfirm = true`；触发 `onConfirmRequired` 回调；ChatBox 用回调 emit `require-confirm` |
| `error` | 设置 `error`，push `❌ 错误：...` |
| `interrupted` | push `⏸️ 已中断` |
| `pong` | 心跳响应，忽略 |

### 7.4 消息渲染（`ChatBox.vue:70-135`）

按 `msg.role` 分三支：

#### 7.4.1 用户消息 `bubble-user`（`ChatBox.vue:73-76`）

- 自身右对齐 `align-self: flex-end`
- `max-width: 70%`，背景 `linear-gradient(135deg, --color-sakura, --color-violet)`
- 圆角 `18px 18px 4px 18px`（右下小切角）
- 进场动画 `slideInRight 300ms var(--ease-spring)`

#### 7.4.2 管家消息 `bubble-agent`（`ChatBox.vue:78-130`）

- 自身左对齐 `align-self: flex-start`
- `max-width: 85%`，玻璃背景
- 圆角 `18px 18px 18px 4px`（左下小切角）
- 进场动画 `slideInLeft 300ms var(--ease-spring)`
- 内容分支：
  - `msg.thinking` 命中 → `.thinking`（`▋` + 斜体半透明文字）
  - 否则 → `.agent-content`：
    1. `<pre>{{ msg.content }}</pre>` 主文本
    2. **项目卡片**（`.project-cards`，`ChatBox.vue:93-110`）：当 `msg.structuredData.projects || msg.structuredData.cards` 存在且非空，渲染 mini-card 网格
       - 每张卡：书名 + 调色板 + `updated_at?.slice(0,10)` + 悬停发光
       - 点击 → `$emit('jump', '/reader/${p.id}/1')`
    3. **跳转按钮**（`.jump-btn`，`ChatBox.vue:111-118`）：当 `msg.structuredData.jump_url` 存在
       - 渐变紫→粉 + arrow-right 图标
       - 点击 → `$emit('jump', msg.structuredData.jump_url)`
    4. **候选项目**（`.candidate-list`，`ChatBox.vue:119-130`）：当 `msg.structuredData.candidates.length > 1`（多项目需要选择时）
       - 每项点击 → `$emit('jump', '/reader/${c.id}/1')`

#### 7.4.3 Tool 消息（`ChatBox.vue:132`）

```vue
<!-- tool 消息不展示（前端不对外展示 TOOL 调用信息） -->
```

注释占位，**完全不渲染**。

> **命名风格不一致说明**：`useStewardChat.ts:130` 把后端返回的 `msg.structured_data`（蛇形命名）赋给本地对象的 `structuredData` 字段（驼峰 key），所以 ChatBox 模板里用 `msg.structuredData` 访问对象本身，而对象内部字段 `projects / jump_url / candidates` 仍是蛇形。这不是 bug，**只是变量命名风格没统一**。

### 7.5 工具调用折叠展示

**无折叠组件**。`tool_calling` / `tool_result` 事件在 `useStewardChat.ts:108-110` 直接被静默忽略，DOM 不会渲染任何 tool 消息。前端用户看不到管家调用了哪些工具。

### 7.6 structured_data 处理全景

后端推送 `agent_message` 时可携带 `structured_data`，字段语义：

| 字段 | 触发条件 | ChatBox 行为 |
|------|----------|--------------|
| `projects` 或 `cards` | 非空数组 | 渲染 `.project-cards` 网格，每张卡点 → `/reader/{id}/1` |
| `jump_url` | 非空字符串 | 渲染 `.jump-btn` 按钮，点 → emit `jump` |
| `candidates` | `length > 1` | 渲染 `.candidate-list`，每项点 → `/reader/{id}/1` |

ChatBox 自身不直接路由跳转，统一 emit `jump(url)` 由父组件决定（Chat.vue 用 `router.push`）。

### 7.7 二次确认弹窗（`ChatBox.vue:137-156`）

- 触发：`requireConfirm = true`（后端 `confirm_required` 事件）
- `.confirm-backdrop` 绝对定位覆盖整个 `.chatbox`（`inset: 0` + `z-index: 100`）
- `.confirm-panel` 居中浮层（`max-width: 400px`）
- 取消 → `onConfirm('danger', false)`
- 确认 → `onConfirm('danger', true)` → 调用 `chat.sendConfirm(action, confirmed)`（`useStewardChat.ts:177-187`）

> **硬编码 `action='danger'`**：当前 UI 不区分 action 类型，固定发送 `danger`（`ChatBox.vue:62-64`），确认逻辑统一处理。

### 7.8 输入栏 + 错误条（`ChatBox.vue:159-179`）

- `.chatbox-input`：textarea + 发送按钮
  - `keydown.enter.exact.prevent="send"` 阻止默认换行
  - `:disabled="chat.thinking || !chat.connected"`（`ChatBox.vue:161-163`）
- `.send-btn` 渐变紫→粉，`disabled` 时 `opacity: 0.4`
- `.error-bar` 仅在 `chat.error` 非空时出现，红色背景 + warning icon

### 7.9 「正在思考」指示器（`ChatBox.vue:126-130`）

独立于消息循环的指示条，出现在消息流末尾，仅在 `chat.thinking.value` 为 true 时渲染，带 `thinking-pulse 2s` 呼吸动画。

### 7.10 样式与响应式

- 容器：`height: 600px; max-height: 700px; min-height: 300px; backdrop-filter: blur(12px)`（`ChatBox.vue:185-194`）
- 移动端 `@media (max-width: 375px)`：user 气泡 85%、agent 95%、发送按钮文字隐藏
- `prefers-reduced-motion` 关闭所有气泡进场 + 光标闪烁动画（`ChatBox.vue:373-381`）

### 7.11 使用位置

当前项目内**仅在 `Chat.vue` 使用**：

| 文件 | 位置 | 备注 |
|------|------|------|
| `views/Chat.vue:8` | `import ChatBox from '@/components/ChatBox.vue'` | — |
| `views/Chat.vue:113-118` | `<ChatBox placeholder="..." :welcome-message="..." @jump="onJump" @require-confirm="..." />` | 路由 `/chat` 落地页 |

> **设计目标**：组件足够通用，未来若 Reader / World 也想嵌入对话，可以直接复用。但当前版本 Reader 的「作者干预」是单行 input + 4 行 textarea（`Reader.vue:184-249`），**没有走 ChatBox 通道**。

---

## 8. 组件复用关系图

```
                       ┌──────────────┐
                       │  router/     │
                       │  index.ts    │  5 路由
                       └──────┬───────┘
                              │
        ┌──────────┬──────────┼──────────┬──────────────┐
        ▼          ▼          ▼          ▼              ▼
   ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
   │ Home   │ │ Chat   │ │ Reader │ │ World    │ │ WorldList│
   │.vue    │ │.vue    │ │.vue    │ │.vue      │ │.vue      │
   └───┬────┘ └───┬────┘ └───┬────┘ └────┬─────┘ └────┬─────┘
       │          │          │           │            │
       │ push     │ 嵌入     │ 嵌入       │            │
       │ '/chat'  │ <ChatBox>│ 干预栏     │            │
       │ '/worlds'│          │ (无 ChatBox)           │
       │          │          │           │            │
       │          ▼          │           ▼            ▼
       │     ┌──────────┐    │   ┌──────────────────────────┐
       │     │ ChatBox  │    │   │ stores/                  │
       │     │ .vue     │    │   │  ├── projects.ts         │
       │     └────┬─────┘    │   │  └── chapters.ts         │
       │          │          │   └──────────────────────────┘
       │          ▼          │           ▲            ▲
       │  ┌────────────────┐ │           │            │
       │  │ useStewardChat │ │           └────────────┘
       │  │ (composable)   │ │
       │  └────┬───────────┘ │
       │       │ WS          │
       │       ▼             │
       │  ws://host/api/chat │
       └─────────────────────┘
```

**复用要点**：

1. **ChatBox 是唯一的对话组件**——通过 `useStewardChat` composable 解耦 WebSocket
2. **stores**：`projectsStore`（`stores/projects.ts`）被 Home/World/Reader/WorldList/Chat 5 个视图共用；`chaptersStore`（`stores/chapters.ts`）被 World/Reader 共用
3. **路由跳转**：Home 通过 `router.push` 触发，WorldList 通过卡片点击触发，Reader 内通过 `goToChapter(n)` 触发
4. **jump 链路**：后端 WS → `useStewardChat.onAgentMessage` 回调 → ChatBox 监听并 emit `jump` → Chat.vue `onJump` → `router.push(url)`（**ChatBox 不直接导航**）
5. **干预 vs 对话**：Reader 底部「作者干预」是**独立实现**的 input（`intervention` 字段），不经过 ChatBox；下一章生成时由 `chaptersStore.generate` 携带 `intervention` 参数

---

## 9. 关键行号速查

| 主题 | 文件 : 行号 |
|------|-------------|
| 5 个路由定义 | `router/index.ts:6-39` |
| Home 启动按钮 push | `Home.vue:104-110` |
| Home 3D orb push | `Home.vue:78-88` |
| Chat 嵌入 ChatBox | `Chat.vue:113-118` |
| World 3 栏 grid | `World.vue:107-167` + `World.vue:288-294` |
| World sticky 危险操作 | `World.vue:269` |
| Reader 2 栏 grid | `Reader.vue:106-180` + `Reader.vue:428-433` |
| Reader 探索度 toggle | `Reader.vue:95-101` + `Reader.vue:392-425` |
| Reader 干预栏 fixed | `Reader.vue:184-249` + `Reader.vue:608-...` |
| Reader drawer 360px | `Reader.vue:254-274` + `Reader.vue:833-900` |
| Reader 响应式 ≤1024px | `Reader.vue:917-924` |
| Reader 响应式 ≤640px | `Reader.vue:925-930` |
| WorldList 三点菜单 | `WorldList.vue:38-41, 167-175` |
| ChatBox Props/Emits | `ChatBox.vue:10-25` |
| ChatBox 内部状态 | `ChatBox.vue:27-29` |
| ChatBox 消息渲染三分支 | `ChatBox.vue:70-135` |
| ChatBox tool 消息不展示 | `ChatBox.vue:132`（注释） |
| ChatBox 二次确认弹窗 | `ChatBox.vue:137-156` |
| ChatBox 错误条 | `ChatBox.vue:177-179` |
| useStewardChat 事件分发 | `useStewardChat.ts:97-156` |
| useStewardChat WS 协议 | `useStewardChat.ts:51-95` |
