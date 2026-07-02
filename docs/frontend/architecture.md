# 前端架构（v0.9.6）

> **版本**：v0.9.6  |  **commit**: e717e5b  |  **最后更新**：2026-07-02
>
> 本文档反映 v0.9.6 实际状态；旧版（v0.5 时期）请见 `docs/frontend/overview.md`（已废弃，仅供考古）。

---

## 1. 元信息

| 项 | 值 |
|---|---|
| 项目名 | `realtime-novel-frontend` |
| 版本 | `0.5.0`（`frontend/package.json:3`）— 文档版本 v0.9.6 独立于 npm version |
| 仓库 commit | `e717e5b` |
| 后端 API 端口 | 7778（`vite.config.ts:20`） |
| 前端 dev server 端口 | 7777（`vite.config.ts:19`） |

> 注：`package.json` 写的是 `0.5.0`，但前端已演进到 v0.9.6 阶段（接入 WS 管家、改 Pinia store、删 Onboarding 路由等），npm version 字段未同步更新，是已知遗留。

---

## 2. 技术栈

版本号取自 `frontend/package.json`。

| 技术 | 版本 | 用途 |
|---|---|---|
| Vue | ^3.5.13 | 前端框架（Composition API + `<script setup>`） |
| TypeScript | ^5.7.2 | 类型安全 |
| Vue Router | ^4.5.0 | SPA 路由（History 模式） |
| Pinia | ^3.0.1 | 状态管理（替代 v0.4 时期的简易 store） |
| Axios | ^1.7.9 | HTTP 客户端 |
| Vite | ^6.0.5 | 构建工具 + dev server |
| @phosphor-icons/vue | ^2.2.1 | 图标库（`ph-sparkle` / `ph-chats-circle` / `ph-globe` 等） |

`devDependencies`：`@vitejs/plugin-vue ^5.2.1`、`vue-tsc ^2.2.0`、`@types/node ^22.10.5`。

---

## 3. 工程结构

```
frontend/
├── public/                              # 静态资源（favicon）
├── src/
│   ├── views/                           # 路由级别页面（懒加载）
│   │   ├── Home.vue                     # 首页（管家大厅）
│   │   ├── Chat.vue                     # 管家对话（独立全屏对话页）
│   │   ├── Reader.vue                   # 章节阅读页（Bento 三栏）
│   │   ├── World.vue                    # 世界管理页
│   │   └── WorldList.vue                # 项目列表页
│   ├── components/
│   │   └── ChatBox.vue                  # 通用聊天组件（569 行，被 Home/Chat 复用）
│   ├── composables/
│   │   └── useStewardChat.ts            # 管家对话 composable（WS 状态机，核心）
│   ├── stores/                          # Pinia
│   │   ├── projects.ts                  # 项目列表 / 当前项目
│   │   ├── chapters.ts                  # 章节列表 / 当前章节 / 生成状态
│   │   └── conversation.ts              # 对话历史（首页聊天，105 行）
│   ├── api/                             # Axios 封装层
│   │   ├── client.ts                    # Axios 实例（baseURL=/api, 120s timeout）
│   │   ├── projects.ts                  # 项目 CRUD（5 端点 + 1 死代码 updateBase）
│   │   ├── chapters.ts                  # 章节 list/read/generate
│   │   └── actions.ts                   # 干预 / 回档 / 图片（3 端点，2 死代码）
│   ├── router/
│   │   └── index.ts                     # 5 个路由配置
│   ├── styles/
│   │   ├── tokens.css                   # 设计 token（颜色/间距/字号/动效）
│   │   ├── base.css                     # 全局基础样式
│   │   └── animations.css               # 动画关键帧（petal-fall、page-slide 等）
│   ├── assets/                          # 图片资源（logo、HOME 主图）
│   ├── App.vue                          # 根组件（导航栏 + RouterView）
│   ├── main.ts                          # 应用入口（注册 Pinia + Router + 3 个 css）
│   └── assets.d.ts                      # 静态资源类型声明
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

---

## 4. 页面路由

路由配置：`frontend/src/router/index.ts:4-39`。

| Path | Name | 组件 | 懒加载 | Props | meta.title |
|---|---|---|---|---|---|
| `/` | `home` | `views/Home.vue` | ✅ (`import()`) | — | 首页 |
| `/chat` | `chat` | `views/Chat.vue` | ✅ | — | 管家对话 |
| `/reader/:projectId/:chapterNum?` | `reader` | `views/Reader.vue` | ✅ | ✅ | 阅读 |
| `/world/:projectId?` | `world` | `views/World.vue` | ✅ | ✅ | 世界 |
| `/worlds` | `world-list` | `views/WorldList.vue` | ✅ | — | 我的世界 |

> 实际有 **5 个**路由（不是 4 个），其中 `Chat` 是 v0.6+ 从 Home 拆出的独立全屏对话页。`chapterNum` 和 `projectId` 都是可选路径参数。

`router/index.ts:54-57` 在 `afterEach` 里根据 `meta.title` 拼接 `document.title`，格式：`{title} · 小说 · 世界`。

---

## 5. 状态管理（Pinia）

3 个 store，在 `main.ts:6-8` 注入：

| Store | 路径 | 职责 |
|---|---|---|
| `useProjectsStore` | `stores/projects.ts`（71 行） | 项目列表 / 当前项目详情 / 创建 / 软删 / 切换探索度 |
| `useChaptersStore` | `stores/chapters.ts`（69 行） | 章节列表 / 当前章节正文 / 生成状态（`generating` flag） |
| `useConversationStore` | `stores/conversation.ts`（105 行） | 首页聊天的对话历史（前端 state，不直接落 DB；持久化走 WS 后端） |

---

## 6. API 层（Axios）

`api/client.ts:13-19` 创建 Axios 实例：

- `baseURL: '/api'`（Vite proxy 转发到 `http://127.0.0.1:7778`，见 `vite.config.ts:25-28`）
- `timeout: 120_000`（120s，章节生成最坏情况）
- 响应拦截器（`client.ts:22-29`）从 `error.response.data.detail` 提取后端 detail 文案到 `error.message`

4 个 API 模块：

| 文件 | 函数 | 备注 |
|---|---|---|
| `api/client.ts` | `healthCheck()` | 死代码（无 caller） |
| `api/projects.ts` | `listProjects / getProject / createProject / deleteProject / updateBase / updateExplorationLevel` | 6 个，1 个死代码（`updateBase`） |
| `api/chapters.ts` | `listChapters / readChapter / generateChapter` | 3 个 |
| `api/actions.ts` | `submitIntervention / rollbackProject / generateImage` | 3 个，2 个死代码 |

**HTTP 端点对齐 + 死代码详情见 `api-integration.md` 第 2.5 节**和 `docs/frontend/api-self-check.md`。

---

## 7. WebSocket 通信

管家对话走 WS，不走 HTTP。

- 端点：`ws://{host}/api/chat`（`composables/useStewardChat.ts:13`，由 `window.location.host` 拼出）
- 单一 composable `useStewardChat`（`composables/useStewardChat.ts:31`）封装状态机
- 状态：`ws / connected / connecting / messages / thinking / error / intent / structuredData / requireConfirm`
- 方法：`connect / send / sendConfirm / close / setOnAgentMessage / setOnConfirmRequired`
- 服务端事件类型：`agent_thinking / tool_calling / tool_result / agent_message / confirm_required / error / interrupted / pong`（7 个，前端全部处理）
- 客户端发送：`{ type: "user_message", content, project_id? }` / `{ type: "confirm", action, confirmed }`（2 种）

**完整事件处理逻辑、字段映射、连接生命周期见 `api-integration.md` 第 3 节。**

---

## 8. 组件体系

| 组件 | 路径 | 行数 | 用途 |
|---|---|---|---|
| `ChatBox.vue` | `src/components/ChatBox.vue` | 569 | 通用聊天组件，封装 `useStewardChat` + 消息渲染（用户/agent/tool/thinking），被 `Home.vue` 和 `Chat.vue` 复用；支持 `structured_data.jump_url` 跳转、confirm 二次确认、工具调用折叠展示 |

其余 UI 全部在 `views/` 页面内 inline 实现（章节列表、bento 布局、干预面板等），无独立小组件抽象。

---

## 9. 样式系统

3 个全局 CSS 文件，在 `main.ts:10-12` 顺序注入：

| 文件 | 内容 |
|---|---|
| `styles/tokens.css` | CSS 变量设计 token（颜色 `--color-*`、间距 `--space-*`、字号 `--text-*`、圆角 `--radius-*`、动效 `--motion-*` / `--ease-*`、阴影 `--shadow-*`、字体 `--font-*`） |
| `styles/base.css` | 全局 reset + body / 滚动条 / 选区等基础样式 |
| `styles/animations.css` | 关键帧动画（`petal-fall` 樱花飘落、`page-slide` 页面切换、`indicator-slide` 导航指示器、`spin` 加载等） |

约定：所有页面/组件用 `<style scoped>`；颜色/间距必须经 CSS 变量引用，禁止硬编码。

---

## 10. 构建与部署

### 脚本（`package.json:6-10`）

| 脚本 | 命令 | 说明 |
|---|---|---|
| `dev` | `vite` | 启动 dev server，端口 7777（`vite.config.ts:24`） |
| `build` | `vue-tsc --noEmit && vite build` | 类型检查 + 打包到 `frontend/dist/` |
| `preview` | `vite preview` | 本地预览生产构建 |

### Vite 反向代理（`vite.config.ts:25-34`）

| 路径前缀 | 目标 | 用途 |
|---|---|---|
| `/api` | `http://127.0.0.1:7778` | REST + WS（`ws: true`） |
| `/openapi.json` | `http://127.0.0.1:7778` | FastAPI 自动生成的 OpenAPI schema |
| `/static` | `http://127.0.0.1:7778` | 静态资源（封面图等，`backend/api/app.py:70-72` 挂载 `/static/projects`） |

`strictPort: true`（`vite.config.ts:24`）— 端口被占直接报错，避免静默换端口。

### 生产部署

**方式 A：FastAPI 静态服务**（`backend/api/app.py:70-72`）

```python
app.mount("/static/projects", StaticFiles(directory=str(_PROJECTS_DATA_DIR)), name="project-static")
```

后端仅服务 `/static/projects/{project_id}/cover.png` 这类项目级静态资源（封面图）。

**方式 B：独立 Nginx**（推荐生产环境）

```nginx
server {
    listen 7777;
    root /path/to/frontend/dist;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }   # SPA fallback
    location /api/   { proxy_pass http://127.0.0.1:7778; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }
    location /static/{ proxy_pass http://127.0.0.1:7778; }
}
```

WS 端点（`/api/chat`）走 `/api/` 代理时需要 Nginx 透传 `Upgrade` / `Connection` 头。

### 启动脚本

`vite.config.ts:8-13` 注释里写明「调整端口：改 `FRONTEND_PORT` / `BACKEND_PORT` 两个常量 + 同步改 `scripts/start.sh`」。启动顺序：先启动后端（`uvicorn backend.api.app:app --port 7778`），再 `npm run dev`。

---

## 11. TypeScript 配置

`tsconfig.json` 关键配置：

| 项 | 值 | 说明 |
|---|---|---|
| `target` | `ES2022` | 现代浏览器目标 |
| `module` | `ESNext` | ESM |
| `moduleResolution` | `bundler` | Vite 风格 |
| `strict` | `true` | 严格模式开启 |
| `noUnusedLocals/Parameters` | `false` | 不检查未使用变量（容忍 v0.5 时期遗留） |
| `jsx` | `preserve` | 由 `vue-tsc` 处理 |
| `baseUrl` | `.` | 路径基准 |
| `paths` | `{ "@/*": ["./src/*"] }` | **`@/` 指向 `src/`**（Vite alias 在 `vite.config.ts:21-23` 同步配置） |
| `include` | `src/**/*.{ts,tsx,vue}` + `vite.config.ts` | 编译范围 |

**`@/` 别名用法**：所有 `.vue` / `.ts` 文件里 `import ChatBox from '@/components/ChatBox.vue'` 等可直接用。
