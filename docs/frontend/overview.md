# 前端技术文档

> **最后更新**：2026-06-29
> **版本**：v0.5.0（frontend package.json）

---

## 目录

1. [技术栈](#1-技术栈)
2. [工程结构](#2-工程结构)
3. [页面路由](#3-页面路由)
4. [状态管理（Pinia）](#4-状态管理)
5. [API 层（Axios）](#5-api-层)
6. [WebSocket 通信（useStewardChat）](#6-websocket-通信)
7. [组件体系](#7-组件体系)
8. [样式系统](#8-样式系统)
9. [构建与部署](#9-构建与部署)

---

## 1. 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue 3 | ^3.5.13 | 前端框架（Composition API + `<script setup>`） |
| TypeScript | ^5.7.2 | 类型安全 |
| Vue Router | ^4.5.0 | SPA 路由 |
| Pinia | ^3.0.1 | 状态管理 |
| Axios | ^1.7.9 | HTTP 客户端 |
| Vite | ^6.0.5 | 构建工具 |
| @phosphor-icons/vue | ^2.2.1 | 图标库 |

---

## 2. 工程结构

```
frontend/
├── src/
│   ├── views/                   # 页面组件（路由级别）
│   │   ├── Home.vue             # 首页（管家大厅）
│   │   ├── World.vue            # 世界管理页
│   │   ├── Reader.vue           # 章节阅读页
│   │   └── WorldList.vue        # 项目列表页
│   ├── components/
│   │   └── ChatBox.vue          # 通用聊天组件（WS 连接 + 消息渲染）
│   ├── composables/
│   │   └── useStewardChat.ts    # 管家对话 composable（WS 状态机）
│   ├── stores/                  # Pinia 状态
│   │   ├── projects.ts          # 项目列表 / 当前项目
│   │   ├── chapters.ts          # 章节列表 / 当前章节 / 生成状态
│   │   └── conversation.ts      # 对话历史（首页聊天）
│   ├── api/                     # Axios API 层
│   │   ├── client.ts            # Axios 实例（baseURL 配置）
│   │   ├── projects.ts          # 项目 CRUD API
│   │   ├── chapters.ts          # 章节 API
│   │   └── actions.ts           # 干预 / 回档 / 图片 / 基座 API
│   ├── router/
│   │   └── index.ts             # 路由配置
│   ├── styles/
│   │   ├── tokens.css           # CSS 变量（设计 token）
│   │   ├── base.css             # 全局基础样式
│   │   └── animations.css       # 动画关键帧
│   ├── App.vue                  # 根组件（路由出口）
│   ├── main.ts                  # 应用入口
│   └── assets.d.ts              # 静态资源类型声明
├── public/
│   └── favicon.png
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

---

## 3. 页面路由

路由配置位于 `src/router/index.ts`。

| 路由 | 组件 | 说明 |
|------|------|------|
| `/` | `Home.vue` | 首页（管家大厅，聊天入口） |
| `/projects` | `WorldList.vue` | 项目列表 |
| `/world/:projectId` | `World.vue` | 项目世界管理页 |
| `/reader/:projectId/:chapterNum` | `Reader.vue` | 章节阅读页 |

所有路由为 SPA 客户端路由（History 模式），刷新需要 Vite dev server 或 nginx 配置 fallback。

---

## 4. 状态管理

### `stores/projects.ts`

管理项目列表和当前项目详情。

**状态**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `projects` | `ProjectInfo[]` | 项目列表 |
| `total` | `number` | 总数 |
| `current` | `ProjectDetail \| null` | 当前项目详情（含 7 件基座） |
| `loading` | `boolean` | 加载中 |
| `error` | `string \| null` | 错误信息 |

**Action**：

| 方法 | 说明 |
|------|------|
| `loadList(limit?)` | 加载项目列表 |
| `loadOne(id)` | 加载单个项目详情 |
| `create(name, palette, initialPrompt?)` | 创建项目 |
| `remove(id)` | 软删除项目（本地立即过滤 + 后台刷新） |
| `updateExplorationLevel(id, level)` | 切换探索度 |

### `stores/chapters.ts`

管理章节列表、当前章节内容、生成状态。

**状态**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `list` | `ChapterMeta[]` | 章节列表（含 title/summary/word_count） |
| `current` | `ChapterDetail \| null` | 当前章节详情（含正文 content） |
| `currentSummary` | `string \| null` | 当前章节概要（抽取的 summary） |
| `generating` | `boolean` | 是否正在生成 |
| `count` | `number` | 章节总数（computed） |

**Action**：

| 方法 | 说明 |
|------|------|
| `loadList(projectId)` | 加载章节列表 |
| `loadOne(projectId, chapterNum)` | 加载单章节（含正文） |
| `generate(projectId, options?)` | 生成下一章（含干预参数） |

### `stores/conversation.ts`

管理首页聊天的对话历史（纯前端状态，不落 DB）。

---

## 5. API 层

### Axios 实例（`api/client.ts`）

```
baseURL = http://127.0.0.1:7778  （后端地址）
timeout = 120_000ms              （章节生成最长 2 分钟）
```

### `api/projects.ts`

```
listProjects(limit?) → { projects: ProjectInfo[], total: number }
getProject(id) → ProjectDetail
createProject(name, palette, initialPrompt?) → { id, name }
deleteProject(id) → { success }
updateExplorationLevel(id, level) → { exploration_level }
```

**ProjectInfo**（列表简版）：

```
{ id, name, palette, exploration_level, cover_image_url, chapter_count, created_at }
```

**ProjectDetail**（详版，含 7 件基座）：

```
{
  ...ProjectInfo,
  world_tree, style_charter, genre_resonance,
  main_plot, sub_plots, character_card, seed_table,
  current_pov, style_pack_id
}
```

### `api/chapters.ts`

```
listChapters(projectId) → ChapterMeta[]
getChapter(projectId, chapterNum) → ChapterDetail
generateChapter(projectId, options?) → ChapterMeta
```

**ChapterMeta**：

```
{ project_id, chapter_num, title, summary, word_count, generated_at }
```

**ChapterDetail**（含正文）：

```
{ ...ChapterMeta, content: string }
```

### `api/actions.ts`

```
submitIntervention(projectId, text) → { success }
rollbackProject(projectId, toChapter) → { success }
generateCoverImage(projectId) → { cover_image_url }
updateArtifact(projectId, artifact, field, value) → { success }
```

---

## 6. WebSocket 通信

WebSocket 是前后端实时通信的核心。管家大厅和项目内聊天都复用同一个 WS 连接。

### `composables/useStewardChat.ts`

```
WS 端点：ws://{host}/api/chat
```

**暴露的状态**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `connected` | `Ref<boolean>` | WS 是否已连接 |
| `connecting` | `Ref<boolean>` | 连接中 |
| `messages` | `Ref<StewardMessage[]>` | 对话消息列表 |
| `thinking` | `Ref<boolean>` | Agent 正在思考 |
| `error` | `Ref<string \| null>` | 错误信息 |
| `intent` | `Ref<string \| null>` | 最近一次 Agent intent |
| `structuredData` | `Ref<Record<string, any> \| null>` | 结构化数据（跳转 URL 等） |
| `requireConfirm` | `Ref<boolean>` | 需要用户二次确认 |

**暴露的方法**：

| 方法 | 说明 |
|------|------|
| `connect()` | 建立 WS 连接 |
| `send(content, projectId?)` | 发送用户消息 |
| `sendConfirm(action, confirmed)` | 发送确认/拒绝 |
| `close()` | 关闭连接 |
| `setOnAgentMessage(fn)` | 注册 agent_message 回调 |
| `setOnConfirmRequired(fn)` | 注册 confirm_required 回调 |

**消息类型（StewardMessage）**：

```
interface StewardMessage {
  role: 'agent' | 'user' | 'system' | 'tool'
  content: string
  toolName?: string           // tool 调用时
  toolArgs?: Record<string, any>
  toolResult?: any
  thinking?: boolean          // LLM 思考中（临时占位）
  timestamp: number
  structuredData?: Record<string, any>  // agent_message 时的结构化数据
}
```

**事件处理逻辑**：

```
服务端 agent_thinking → 添加 thinking 消息（临时占位）
服务端 tool_calling   → 添加工具调用消息
服务端 tool_result    → 添加工具结果消息
服务端 agent_message  → 替换最后一条 thinking 消息为最终回复
                        （保证消息流视觉上是连续的，不是叠加）
服务端 confirm_required → requireConfirm.value = true
服务端 error          → error.value = message
服务端 interrupted    → thinking.value = false
```

**连接生命周期**：

- `onMounted` 时（在 `ChatBox.vue` 内）调 `connect()`
- `onUnmounted` 时自动调 `close()`（`useStewardChat` 内注册）
- WS 断开后不自动重连（业务层决定是否重连）

---

## 7. 组件体系

### `ChatBox.vue`（通用聊天组件）

最核心的可复用组件，被 `Home.vue` 使用。

**Props**：

| Prop | 类型 | 说明 |
|------|------|------|
| `placeholder` | `string` | 输入框占位文字 |
| `welcomeMessage` | `string` | 欢迎语（首次显示） |

**Emits**：

| 事件 | 说明 |
|------|------|
| `jump(url: string)` | 管家返回了 `structured_data.jump_url` 时触发，让父组件执行路由跳转 |
| `require-confirm(action)` | 危险操作需要二次确认时触发 |

**功能**：
- 内部使用 `useStewardChat` composable 管理 WS 连接
- 渲染消息列表（用户消息 / agent 消息 / tool 调用过程 / thinking 占位）
- 工具调用折叠展示（默认折叠，可展开查看详情）
- `structured_data.jump_url` 自动 emit `jump` 事件

### `Home.vue`（首页）

管家大厅模式，以聊天为主界面：

- 顶部导航：logo + 标题 + 「我的项目」按钮
- 主区域：`ChatBox` 全屏聊天（`project_id` 为 null，大厅模式）
- 浮层：点击「我的项目」弹出项目卡片网格（最多 7 个）

### `World.vue`（世界管理页）

项目信息总览，3 栏布局：

| 栏 | 内容 |
|---|------|
| 左（240px） | 项目信息（章节数/色调）+ 进入阅读按钮 |
| 中 | 章节列表（可滚动，每行点击进入阅读） |
| 右（240px） | 危险操作（回档 + 删除），sticky 吸顶 |

顶部：世界封面图 Banner（有图展示，无图占位）

### `Reader.vue`（章节阅读页）

3 栏 Bento 布局，章节阅读核心页：

| 栏 | 宽度 | 内容 |
|---|------|------|
| 左 | 200px | 封面缩略图 + 章节导航（上/下章）+ 进度条 |
| 中 | 1fr | 本章概要胶囊 + 章节标题 + 正文 + 章尾「生成下一章」 |
| 右 | 280px | 干预面板（输入框 + 记录按钮），sticky 吸顶 |

顶部：封面图折叠 Banner（可展开/收起）

**顶部工具栏**：
- 返回按钮 → `/world/:projectId`
- 项目名称 + palette 标签
- 探索度下拉（conservative/standard/wild）
- 章节列表 Drawer 开关

**章节 Drawer**（右侧滑入抽屉）：
- 展示全部章节列表
- 每行：章节序号 + 标题 + summary 摘要
- 点击跳转到对应章节

响应式：宽度 < 1024px 时切换为单栏布局。

---

## 8. 样式系统

基于 CSS 自定义属性（CSS Variables）构建设计 token 系统。

### `styles/tokens.css`（设计 token）

**颜色（深色主题）**：

```
--color-night-1: #0a0514;     /* 最深背景 */
--color-night-2: #130d20;     /* 卡片/面板背景 */
--color-night-3: #1e1530;     /* 次级元素背景 */

--color-accent-1: #ff8fb1;    /* 主强调色（粉红） */
--color-accent-2: #a78bfa;    /* 次强调色（紫） */
--color-accent-3: #8b5cf6;    /* 第三强调色（深紫） */

--color-text: rgba(255,255,255,0.92);
--color-text-dim: rgba(255,255,255,0.55);
--color-text-faint: rgba(255,255,255,0.3);

--color-error: #f87171;
```

**间距（4px 基准）**：

```
--space-1: 4px;   --space-2: 8px;   --space-3: 12px;
--space-4: 16px;  --space-5: 24px;  --space-6: 32px;  --space-7: 48px;
```

**字体**：

```
--font-body: 'Noto Serif SC', serif;   /* 正文（小说阅读） */
--font-ui: 'Noto Sans SC', sans-serif; /* UI 元素 */
--font-mono: 'Fira Code', monospace;   /* 章节序号等 */
```

**字号**：

```
--text-xs: 11px;  --text-sm: 13px;  --text-base: 15px;
--text-lg: 18px;  --text-xl: 20px;  --text-2xl: 24px; --text-3xl: 30px;
```

**圆角**：

```
--radius-sm: 4px;  --radius-md: 8px;
--radius-lg: 16px; --radius-full: 9999px;
```

**动效**：

```
--motion-fast: 150ms;
--motion-base: 250ms;
--ease-out: cubic-bezier(0.16, 1, 0.3, 1);
```

**阴影**：

```
--shadow-glow: 0 0 20px rgba(255,143,177,0.3);  /* 主按钮发光 */
```

### `styles/animations.css`

常用动画关键帧：

```
@keyframes spin { ... }           /* 加载 Spinner */
@keyframes fade-in { ... }        /* 内容渐入 */
@keyframes slide-up { ... }       /* 卡片上滑出现 */
```

### 样式约定

- **Scoped 样式优先**：所有页面/组件样式都用 `<style scoped>`，避免全局污染
- **CSS 变量强制要求**：禁止硬编码颜色值，全部通过 `var(--color-xxx)` 引用
- **响应式**：通过 `@media (max-width: 1024px)` 处理平板/手机布局
- **过渡动画**：交互过渡统一使用 `transition: all var(--motion-fast) var(--ease-out)`

---

## 9. 构建与部署

### 开发模式

```bash
cd frontend
npm run dev -- --port 7777
```

Vite 配置了反向代理，将 `/api/` 请求转发到后端：

```
// vite.config.ts
server: {
  proxy: {
    '/api': 'http://127.0.0.1:7778',
    '/static': 'http://127.0.0.1:7778',
  }
}
```

### 生产构建

```bash
npm run build
```

产出到 `frontend/dist/`（已 gitignore）。

构建包括：
- `vue-tsc --noEmit`：TypeScript 类型检查（构建失败则类型有误）
- Vite 打包：代码分割 + Hash 文件名（长期缓存）
- 资源分块：每个 View 独立 chunk（懒加载）

### 生产部署

**方式一**：FastAPI 静态文件服务（当前方式）

```python
# backend/api/app.py（如需静态服务）
app.mount("/", StaticFiles(directory="frontend/dist", html=True))
```

**方式二**：独立 Nginx 服务（推荐生产环境）

```
server {
    listen 7777;
    root /path/to/frontend/dist;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }  # SPA fallback
    location /api/ { proxy_pass http://127.0.0.1:7778; }
    location /static/ { proxy_pass http://127.0.0.1:7778; }
}
```

### TypeScript 配置

`tsconfig.json` 主要配置：

```
{
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "strict": true,
    "jsx": "preserve",
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  }
}
```

`@/` 路径别名指向 `src/`，在所有 `.vue` 和 `.ts` 文件中可用。

