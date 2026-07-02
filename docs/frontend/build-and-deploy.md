# 前端构建与部署（Build & Deploy）

> **元信息**
> - 日期：2026-07-02
> - 版本：v0.9.6
> - Commit：e717e5b
> - 项目：realtime-novel
> - 适用范围：frontend 构建、开发、部署

---

## 1. 端口约定

### 1.1 当前端口（v0.6 起，hardcoded）

| 角色 | 端口 | 备注 |
|------|------|------|
| 前端 dev server | **7777** | Vite 开发模式 |
| 后端 API | **7778** | uvicorn 服务 |
| API 代理 | `/api` → `http://127.0.0.1:7778` | 由 vite.config.ts 配 |
| WebSocket 代理 | `/api` 同上，`ws: true` | Vite 配 |
| OpenAPI 文档 | `/openapi.json` → 后端 7778 | 调试用 |
| 静态资源代理 | `/static` → 后端 7778 | 配 StaticFiles |

> 端口来源（**单一来源原则**）：
> - `frontend/vite.config.ts:14-15`：`FRONTEND_PORT=7777` / `BACKEND_PORT=7778`
> - `scripts/start.sh:13-15`：同上三个常量
> - 调整端口：**两个文件必须同步修改**

### 1.2 ⚠️ 已知文档错误

`frontend/src/api/client.ts:4` 注释里写：

```typescript
* 后端实际端口：见 vite.config.ts 的 BACKEND_PORT（当前 7777）
```

**这是错的**。v0.6 起后端实际端口是 **7778**，注释里写的 7777 与实际不符（7777 是前端 dev server 端口）。

**修正建议**：把 `client.ts:4` 改为：

```typescript
* 后端实际端口：见 vite.config.ts 的 BACKEND_PORT（当前 7778）
```

> 该注释不影响运行（axios 走 `/api` 路径，由 Vite 代理转发，不直接连后端），但会给读代码的人造成误导。

---

## 2. 开发模式

### 2.1 启动命令

```bash
# 方式一：一键启动（推荐）
scripts/start.sh
# 效果：先后端再前端，日志在 tmp/logs/{backend,frontend}.log

# 方式二：手动分别启动
# 终端 A — 后端
.venv/bin/uvicorn backend.api.app:app --host 127.0.0.1 --port 7778

# 终端 B — 前端
cd frontend && npm run dev
```

> 来源：`scripts/start.sh:1-15`（端口常量）+ `package.json:7`（dev 脚本）

### 2.2 vite 反向代理配置

> 文件：`frontend/vite.config.ts:22-43`

| 路径前缀 | 目标 | changeOrigin | ws | 用途 |
|----------|------|--------------|-----|------|
| `/api` | `http://127.0.0.1:7778` | ✅ | ✅ | REST API + WebSocket |
| `/openapi.json` | `http://127.0.0.1:7778` | ✅ | ❌ | OpenAPI schema（调试） |
| `/static` | `http://127.0.0.1:7778` | ✅ | ❌ | 后端 StaticFiles |

**关键配置**：

```typescript
server: {
  port: FRONTEND_PORT,        // 7777
  strictPort: true,           // 端口被占就报错，不静默换端口
  proxy: { ... }
}
```

- `strictPort: true`：`vite.config.ts:27` — 防止端口冲突时静默切到 7778
- `ws: true`：仅 `/api` 配了 WebSocket 代理（用于 SSE/实时通信）
- `changeOrigin: true`：所有代理都开启（修 Host 头，避免后端校验失败）

### 2.3 路径别名

`vite.config.ts:18-21`：

```typescript
resolve: {
  alias: {
    '@': fileURLToPath(new URL('./src', import.meta.url))
  }
}
```

含义：源码中 `@/components/Foo.vue` 等价于 `frontend/src/components/Foo.vue`。

### 2.4 浏览器访问

启动后浏览器打开 `http://localhost:7777/`：

- 前端页面走前端 dev server
- API 请求走 `/api/*` → Vite 代理 → 后端 7778
- WebSocket 走 `/api/*` → Vite ws 代理 → 后端 7778

> 来源：`scripts/start.sh:163-164`（启动完成提示）

---

## 3. 生产构建

### 3.1 构建命令

```bash
cd frontend
npm run build
```

> 来源：`package.json:8` — `"build": "vue-tsc --noEmit && vite build"`

**两个阶段**：

1. **`vue-tsc --noEmit`**：TypeScript + Vue 模板的类型检查，不输出文件
   - 严格模式（`tsconfig.json:13` `strict: true`）
   - 检查所有 `.vue` / `.ts` / `.tsx`
2. **`vite build`**：打包
   - 入口 `index.html`（通过 `<script type="module" src="/src/main.ts">` 引入）
   - 输出到 `frontend/dist/`

### 3.2 构建产物

```
frontend/dist/
├── index.html              # 入口 HTML（script/link 已 inline 化）
├── assets/
│   ├── index-[hash].js     # 业务代码 + Vue 运行时
│   ├── index-[hash].css    # 提取后的 CSS（tokens + base + animations + 组件）
│   └── ...                 # 按需 chunk
└── favicon.png             # 来自 public/
```

### 3.3 预览构建产物

```bash
cd frontend
npm run preview
# 启 Vite preview server，默认 4173 端口
```

> 来源：`package.json:9`

仅本地验证用，**不用于生产部署**。

---

## 4. 部署方式

### 4.1 方式一：FastAPI 静态文件服务（一体化）

把构建产物挂到 FastAPI app 上，单端口对外服务。

**步骤**：

1. 构建前端
   ```bash
   cd frontend && npm run build
   ```
2. 在 FastAPI 入口（`backend/api/app.py`）挂载：
   ```python
   from fastapi.staticfiles import StaticFiles
   app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")
   app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="spa")
   ```
3. 用 `uvicorn backend.api.app:app --port 7778` 启动
4. 访问 `http://127.0.0.1:7778/`（注意：**是后端端口**）

**优点**：

- 单一进程，无 CORS
- API 和前端同源
- 部署最简单

**缺点**：

- FastAPI 性能不如 Nginx（静态文件）
- 没有 CDN 缓存

**适用场景**：demo / 内网 / 单机部署。

### 4.2 方式二：独立 Nginx（**推荐生产**）

Nginx 同时托管静态文件 + 反向代理 API。

**步骤**：

1. 构建前端到 `frontend/dist/`
2. Nginx 配置示例：
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       root /path/to/realtime-novel/frontend/dist;
       index index.html;

       # SPA fallback
       location / {
           try_files $uri $uri/ /index.html;
       }

       # 静态资源缓存
       location /assets/ {
           expires 1y;
           add_header Cache-Control "public, immutable";
       }

       # API 反代
       location /api/ {
           proxy_pass http://127.0.0.1:7778;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       # OpenAPI
       location = /openapi.json {
           proxy_pass http://127.0.0.1:7778;
       }

       # WebSocket
       location /api/ws/ {
           proxy_pass http://127.0.0.1:7778;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
       }
   }
   ```
3. 后端用 systemd 跑 `uvicorn`（仅暴露在 127.0.0.1:7778）
4. 启动：`systemctl reload nginx`

**优点**：

- 静态文件高性能（sendfile / gzip / 缓存）
- 天然支持 WebSocket upgrade
- HTTPS / 限流 / 日志全套
- 前端可走 CDN

**缺点**：

- 多一个进程要管
- 配置比方式一复杂

**适用场景**：生产环境、正式服务、有 HTTPS 需求。

### 4.3 部署流程对比

| 阶段 | 方式一（FastAPI） | 方式二（Nginx） |
|------|-------------------|------------------|
| 构建 | `npm run build` | `npm run build` |
| 部署 | 挂 `frontend/dist` 到 FastAPI | 上传 `frontend/dist` 到服务器 + Nginx reload |
| 端口 | 后端 7778 | Nginx 80/443 |
| HTTPS | 需在 FastAPI 上配 | Nginx 一行配置 |
| WebSocket | 需 uvicorn `--ws` | `proxy_set_header Upgrade` |
| 性能 | 一般 | 高 |
| 复杂度 | ⭐ | ⭐⭐⭐ |

---

## 5. TypeScript 配置

> 文件：`frontend/tsconfig.json`

### 5.1 关键字段

| 字段 | 值 | 说明 |
|------|------|------|
| `target` | `ES2022` | 编译目标 |
| `useDefineForClassFields` | `true` | 类字段语义对齐 ES2022 |
| `module` | `ESNext` | 模块系统 |
| `lib` | `["ES2022", "DOM", "DOM.Iterable"]` | 类型库 |
| `moduleResolution` | `bundler` | Vite 推荐配置 |
| `allowImportingTsExtensions` | `true` | 允许 `import './foo.ts'` |
| `isolatedModules` | `true` | 强制单文件编译（Vite 必需） |
| `moduleDetection` | `"force"` | 强制模块检测 |
| `noEmit` | `true` | 不输出文件（Vite 接管） |
| `jsx` | `"preserve"` | JSX 由 Vite 处理 |
| **`strict`** | **`true`** | 严格模式（必检空值/类型） |
| `noUnusedLocals` | `false` | 不强制未用局部变量报错 |
| `noUnusedParameters` | `false` | 不强制未用形参报错 |
| `noFallthroughCasesInSwitch` | `true` | switch case 必须 break |
| `esModuleInterop` | `true` | 允许 `import x from 'y'` |
| `resolveJsonModule` | `true` | 支持 import JSON |
| **`baseUrl`** | **`.`** | 路径基准 |
| **`paths`** | **`{"@/*": ["./src/*"]}`** | `@/` 指向 `src/` |

### 5.2 include 范围

```json
"include": [
  "src/**/*.ts",
  "src/**/*.tsx",
  "src/**/*.vue",
  "vite.config.ts"
]
```

包含全部源码 + Vite 配置。

### 5.3 与 Vite 的关系

- `tsconfig.json` 负责**类型检查**（`vue-tsc` 阶段）
- `vite.config.ts` 的 `alias` 负责**运行时解析**（构建阶段）
- 两者的 `@/*` 必须保持一致

---

## 6. 启动脚本

### 6.1 scripts/start.sh（一键启动）

> 文件：`scripts/start.sh`

**流程**（`main()` 函数 `start.sh:153-176`）：

1. **打印横幅**（`start.sh:155-159`）：显示前后端 URL
2. **check_llm_api_key**（`start.sh:38-58`）：
   - 检查 `.llm_api_key` 文件存在
   - 校验 JSON 格式正确
   - 校验通过输出 `✓ .llm_api_key JSON 校验通过`
3. **check_dependencies**（`start.sh:61-68`）：
   - 检查 `.venv/` 存在
   - 检查 `frontend/node_modules/` 存在
4. **kill_port_if_used**（`start.sh:71-114`）：
   - 用 `lsof -i :7778` 查后端端口占用
   - 用 `lsof -i :7777` 查前端端口占用
   - **白名单判断**：进程 cmdline 含 `realtime.novel` / `uvicorn.*backend.api` / `backend.api.app` / `vite --port <port>` / 项目根路径 → 视为本项目进程，kill
   - 命中非项目进程 → 报错退出（不静默 kill）
5. **start_backend**（`start.sh:117-135`）：
   - `nohup uvicorn backend.api.app:app --host 127.0.0.1 --port 7778 > tmp/logs/backend.log 2>&1 &`
   - 把 PID 写入 `tmp/pids/backend.pid`
   - 轮询 `http://127.0.0.1:7778/api/health`，15s 内就绪算成功
6. **start_frontend**（`start.sh:138-151`）：
   - `nohup npm run dev -- --port 7777 > tmp/logs/frontend.log 2>&1 &`
   - 把 PID 写入 `tmp/pids/frontend.pid`
   - 轮询 `http://localhost:7777/`，15s 内就绪算成功
7. **打印使用提示**（`start.sh:166-171`）

**关键路径**：

| 用途 | 路径 |
|------|------|
| 后端日志 | `tmp/logs/backend.log` |
| 前端日志 | `tmp/logs/frontend.log` |
| 后端 PID | `tmp/pids/backend.pid` |
| 前端 PID | `tmp/pids/frontend.pid` |
| LLM API key | `.llm_api_key`（gitignored） |

### 6.2 scripts/stop.sh（一键停止）

> 文件：`scripts/stop.sh`

**流程**：

1. 读 `tmp/pids/backend.pid`，`kill <pid>`，等 5s 退出；还活着就 `kill -9`（`stop.sh:5-27`）
2. 读 `tmp/pids/frontend.pid`，同样逻辑
3. 删除 pidfile

**注意**：

- 依赖 `tmp/pids/*.pid` 文件存在（start.sh 启动时创建）
- 如果 start.sh 被强杀，pidfile 还在，stop.sh 仍可清理
- 如果 pidfile 不存在，会跳过并提示

### 6.3 开发工作流

```bash
# 第一次
git clone ...
python -m venv .venv
.venv/bin/pip install -e .
cd frontend && npm install
echo '{"FRIDAY_API_KEY":"xxx"}' > ../.llm_api_key
chmod 600 ../.llm_api_key

# 日常
scripts/start.sh     # 启动
# ... 写代码 ...
scripts/stop.sh      # 停止
```

---

## 7. 依赖

### 7.1 package.json 速查

> 文件：`frontend/package.json`

| 依赖 | 版本 | 用途 |
|------|------|------|
| `vue` | ^3.5.13 | 框架 |
| `vue-router` | ^4.5.0 | 路由 |
| `pinia` | ^3.0.1 | 状态管理 |
| `axios` | ^1.7.9 | HTTP |
| `@phosphor-icons/vue` | ^2.2.1 | 图标库 |

| devDependency | 版本 | 用途 |
|---------------|------|------|
| `@vitejs/plugin-vue` | ^5.2.1 | Vite Vue 插件 |
| `typescript` | ^5.7.2 | TS 编译 |
| `vue-tsc` | ^2.2.0 | Vue 模板类型检查 |
| `vite` | ^6.0.5 | 构建工具 |
| `@types/node` | ^22.10.5 | Node 类型 |

> 来源：`package.json:13-30`

### 7.2 脚本命令

| 命令 | 行为 |
|------|------|
| `npm run dev` | Vite dev server（带热更新） |
| `npm run build` | `vue-tsc --noEmit && vite build` |
| `npm run preview` | 启动 Vite preview server |

> 来源：`package.json:6-9`

### 7.3 字体与图标（CDN 加载）

`index.html:7-9`：

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:...&family=Plus+Jakarta+Sans:...&family=Noto+Sans+SC:...&family=JetBrains+Mono:...&family=Zen+Maru+Gothic:...&display=swap" rel="stylesheet">
<script src="https://unpkg.com/@phosphor-icons/web"></script>
```

- **字体**：从 Google Fonts 加载（Noto Serif SC / Plus Jakarta Sans / Noto Sans SC / JetBrains Mono / Zen Maru Gothic）
- **图标**：Phosphor Icons（unpkg CDN）

> 离线环境需要替换成本地资源。

---

## 8. 完整工作流（开发到生产）

### 8.1 本地开发

```bash
# 一键启动
scripts/start.sh
# 浏览器开 http://localhost:7777/
# 改代码自动热更新
# 改 backend 也热更新（uvicorn reload 在生产配置里需 --reload）

# 看日志
tail -f tmp/logs/backend.log
tail -f tmp/logs/frontend.log

# 停止
scripts/stop.sh
```

### 8.2 生产部署（方式二：Nginx）

```bash
# 1. 拉代码
git clone ...
cd realtime-novel
git checkout v0.9.6   # 锁版本

# 2. 安装依赖
python -m venv .venv
.venv/bin/pip install -e .
cd frontend && npm ci && cd ..

# 3. 配 LLM key
echo '{"FRIDAY_API_KEY":"prod_key"}' > .llm_api_key
chmod 600 .llm_api_key

# 4. 构建前端
cd frontend && npm run build && cd ..

# 5. 启动后端（systemd 托管）
sudo systemctl start realtime-novel-backend

# 6. 配置 Nginx（参考 §4.2）
sudo vim /etc/nginx/conf.d/realtime-novel.conf
sudo nginx -t
sudo systemctl reload nginx

# 7. 验证
curl http://your-domain.com/
curl http://your-domain.com/api/health
```

### 8.3 回滚

```bash
# 切到上一个 tag
git checkout v0.9.5

# 重新构建
cd frontend && npm run build && cd ..

# 重启后端
sudo systemctl restart realtime-novel-backend

# Nginx 不需要动（dist 路径不变）
```

---

## 9. 检查清单

部署到生产前确认：

- [ ] `.llm_api_key` 配好且 `chmod 600`
- [ ] 前端构建产物 `frontend/dist/` 存在
- [ ] 后端用 systemd / supervisor 托管
- [ ] Nginx 配置 `try_files` SPA fallback
- [ ] Nginx 配置 `proxy_set_header Upgrade` 支持 WebSocket
- [ ] API 走同源（前端 `/api` 代理到后端）
- [ ] 静态资源 `Cache-Control: public, immutable`
- [ ] 端口 7777 / 7778 防火墙放行（或改 Nginx 统一 80/443）
- [ ] `client.ts:4` 注释里 7777 错字已修正为 7778
- [ ] 日志目录 `tmp/logs/` 定期轮转
