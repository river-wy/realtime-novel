# Novel Novel · 整体路线图

> **创建**：2026-06-16（蕾姆酱应欧尼酱要求重写）
> **作用**：一张表/一段话能让任何新人秒懂这个项目在做什么、做到哪、下一步做什么
> **状态**：✅ 骨架阶段完成 · ⏳ API 化阶段待启动 · ⏳ 前端阶段待启动

---

## 🎯 30 秒摘要

Novel Novel = **AI 实时生成小说的读者+创作者 Web 平台**。你想读小说，AI 给你写；你想改剧情，你说话 AI 立刻响应；你想回到前面，AI 帮你回档。

工程进展：
- ✅ **后端骨架做完** —— AI 能生成章节、能干预、能回档（命令行跑得通）
- ⏳ **后端 API 化** —— 上面这些能力要变成 HTTP 接口，前端才能调（**下一步要做的**）
- ⏳ **前端页面** —— 做 4 个页面（首页 / 启动新世界 / 章节阅读 / 世界管理），4 个 demo HTML 已经审过了

**3 个大阶段做完 = 产品上线**。

---

## 📊 3 大阶段一览

| # | 阶段 | 一句话 | 状态 | 产出 |
|---|------|--------|------|------|
| **1** | **后端骨架** | 让 AI 真的能生成小说 + 干预 + 回档 | ✅ **完成**（2026-06-15）| 5 个服务 + 17 项验收全过 |
| **2** | **后端 API 化** | 把上面能力变成 HTTP 接口，前端能调 | ⏳ **待启动** | 5 个 HTTP 路由（projects / chapters / onboarding / interventions / rollback）|
| **3** | **前端页面** | 做 4 个用户能看的页面 | 🟡 **部分完成** | design-spec（4 份）+ demo HTML（4 份）已审过 · 真实 Vue 工程待做 |

**当前在做**：阶段 2 — 后端 API 化（用 `backend-spec-dev-harness` 跑 S0-S7）
**做完阶段 2 才进**：阶段 3 的真实 Vue 工程开发

---

## 📖 阶段 1：后端骨架（已完成）

### 做了什么

让产品「跑得通」—— 5 个核心能力全部实现 + 跑测试 + 全部通过：

| 能力 | 说明 | 状态 |
|------|------|------|
| **项目管理** | 创建 / 读取 / 列出 / 删除小说项目 | ✅ |
| **章节生成** | AI 根据项目设定写下一章（约 60-100 秒出 3000-4500 字）| ✅ |
| **启动新世界** | 5 步引导：选标签 → 选调色板 → 自由文本 → 大纲 → AI 自动生成 7 件 + 第 1 章 | ✅ |
| **剧情干预** | 用户输入想法，AI 解析后调整下一章走向 | ✅ |
| **章节回档** | 回到任意之前章节，node 树截断，章节重生成 | ✅ |

**关键技术**：Python 3.12 + LLM 端到端生成 + 7 件 Pydantic Schema 持久化 + 4 维种子权重算法

### 怎么跑

```bash
# 启动后端 CLI
cd /Users/wuyu/creativeToys/realtime-novel
python -m realtime_novel <command> <args>
```

**支持命令**：`create / load / list / delete / generate / intervene / rollback / onboarding run`

### 详细记录

`v0.3-completion.md.legacy`（收口报告快照，所有里程碑详情 + 17 项验收 + commit 历史）— 写完永不变，外人要看历史只读这个。

### 路线图演进（保留作交叉引用）

阶段 1 在旧路线图里叫 **v0.3 骨架阶段**，由 4 个内部里程碑 M-α / M-β / M-γ / M-δ 组成：
- M-α：项目管理 + 世界树（7 件 Schema 落盘）
- M-β：章节生成（接 LLM 端到端）
- M-γ：5 步启动链路
- M-δ：干预 + 回档

**新路线图不再用 M-α 这种代号**（看不懂），但**commit message 和 commit hash 里还有**（保留做代码层溯源）。

---

## 📖 阶段 2：后端 API 化（待启动）⭐ **下一步**

### 要做什么

把阶段 1 的 5 个 CLI 命令变成 **5 个 HTTP 路由**，让前端能通过 HTTP 调：

| 路由 | 方法 | 作用（对应阶段 1 能力）|
|------|------|------------------------|
| `/api/projects` | GET / POST | 列出 / 创建项目 |
| `/api/projects/{id}` | GET / DELETE | 读取 / 删除项目 |
| `/api/projects/{id}/chapters/{n}` | GET | 读指定章节 |
| `/api/projects/{id}/chapters` | POST | 生成下一章 |
| `/api/projects/{id}/onboarding/run` | POST | 5 步启动链路 |
| `/api/projects/{id}/interventions` | POST | 提交剧情干预 |
| `/api/projects/{id}/rollback` | POST | 回档到指定章节 |
| `/api/projects/{id}/image` | POST | 生成项目主立绘（LLM 图像）|
| `/api/health` | GET | 健康检查 |
| `/api/info` | GET | 版本信息 |

**技术栈**：FastAPI + Uvicorn + Pydantic v2（已定）· **不引** Redis / MQ 等中间件（M-ε 阶段单机就够）

### 怎么启动

用 `backend-spec-dev-harness` skill 跑 8 步（**S0 → S1 → S2 → S3 → S4 → S5 → S6 → S7**）：
- S0 后端基线检查（FastAPI 选型 + Pydantic v2 + 已有服务清单）
- S1 API 规范生成（spec.md — 上面这张路由表细化）
- S2 服务/路由拆分（哪些路由对应哪些 service）
- S3 技术方案设计（接口参数 + 异常处理 + 鉴权）
- S4 测试用例设计（curl + pytest 集成测试）
- S5 代码生成
- S6 测试代码生成
- S7 测试验收

**预计 5-7 天**（按每个里程碑 1 天估）。

### 怎么算完成

- 5 个路由全部上线
- pytest 全过
- curl 能跑通 demo-urban-romance 完整链路（创建项目 → 启动 → 读章节 → 干预 → 回档）
- 错误处理完备（404 / 422 / 500 都有明确响应）
- 文档：OpenAPI 自动生成（FastAPI 自带）+ 1 份人话版 API 文档

### 详细方案

阶段 2 启动时会在 `.backend-spec/` 下生成完整 spec.md / modules.json / arch-plan/ / test-cases/ / verify-report.md — 这些是 S7 验收的依据。

---

## 📖 阶段 3：前端页面（部分完成）

### 现状

| 子阶段 | 状态 | 产出 |
|--------|------|------|
| **设计稿**（4 页面长什么样）| ✅ done | `.spec/m-epsilon/design-specs/{home,onboarding,reader,world}.md`（共 3,240 行）|
| **Demo HTML**（用 HTML+CSS 验证设计是否对）| ✅ done | `.spec/m-epsilon/demo/{home,onboarding,reader,world}.html`（共 ~5,000 行，**已审过，基调对齐**）|
| **真实工程**（Vue 3 工程实现）| ⏳ pending | 等阶段 2 后端 ready 才能开 |

### 4 个页面

| 页面 | 作用 | 设计基线 |
|------|------|----------|
| **首页** | 项目门户：立绘 + 「新启动」/「打开 demo」入口 | 樱色夜空主色 + 二次元 chibi |
| **启动新世界** | 5 步引导新项目（标签 / 调色板 / 自由文本 / 大纲 / AI 自动生成）| 终端风格确认框 |
| **章节阅读** | 沉浸阅读 + 干预输入（剧情干预 always-on + 演员模式开关）| 65ch 衬线正文 + 灵动 motion |
| **世界管理** | 项目深度管理 + node 树 + 终端风格回档 | 终端 chrome + node 树 |

### 怎么做

- **框架**：Vite 5 + Vue 3.5 + TypeScript + Pinia + Vue Router + Axios
- **样式**：Vanilla CSS + CSS 变量（**不引** Tailwind/UI 库）
- **图标**：Phosphor Icons（**不引** Lucide）
- **API 客户端**：baseURL = `http://127.0.0.1:8080/api`（阶段 2 部署后切换）
- **设计规范 subskill**：`novel-novel-design` v1.0（樱色夜空 #1B0F2E + 强调 #FF8FB1 / #FFC857 / #8B5CF6，3-DIAL 7/8/3）

### 怎么算完成

- 4 页面在 `http://localhost:5173` 跑得通
- 跟后端联调成功（创建项目 → 读章节 → 干预 → 回档）
- 桌面 1440×900 + 平板 1024×768 + H5 375×667 三档响应式
- LCP < 2s / CLS < 0.1
- 真实浏览器验收（4 页面设计清单每条都过）

### 路线图演进

阶段 3 在旧路线图里叫 **M-ε**（Novel Novel 前端 UI 子项目），由 6 个内部步骤 S1-S6 组成：
- S1 需求澄清
- S2 页面清单
- S3 设计稿（已 done）
- S4 Demo 验证（已 done）
- S5 真实工程开发（**当前**）
- S6 浏览器验收

---

## 🗓️ 整体时间线

```
2026-06-15 ▓▓▓▓▓▓▓▓▓▓ 后端骨架（M-α/β/γ/δ 4 里程碑）✅
2026-06-16 ░░░░░░░░░░ 后端 API 化（待启动）
2026-06-XX ░░░░░░░░░░ 前端页面 S5（待阶段 2 完成）
2026-06-XX ░░░░░░░░░░ 前端页面 S6（待 S5 完成）
2026-06-XX ░░░░░░░░░░ 产品上线 🎉
```

---

## 🔗 关键文档索引

| 想了解 | 看 |
|--------|----|
| **后端骨架详细做了什么** | `v0.3-completion.md.legacy`（4 里程碑详情 + 17 项验收）|
| **后端骨架路线图演进** | `v0.3-product-skeleton.md.legacy`（旧版路线图，保留做历史溯源）|
| **前端 4 页面设计稿** | `../.spec/m-epsilon/design-specs/`（4 份 design-spec）|
| **前端 4 页面 demo** | `../.spec/m-epsilon/demo/`（4 份 demo HTML，可浏览器访问）|
| **后端 API 化规范** | 阶段 2 启动后会生成在 `../.backend-spec/` |
| **前端设计规范 subskill** | `~/.agents/skills/novel-novel-design/`（待装） |
| **harness 编排层** | `~/.openclaw/agents/main/agent/skills/backend-spec-dev-harness/`（8 步编排层）|

---

## 🤝 谁在负责

| 阶段 | 负责 |
|------|------|
| 1 后端骨架 | 蕾姆酱（已交付）|
| 2 后端 API 化 | 蕾姆酱（待启动）|
| 3 前端页面 | 蕾姆酱（设计稿/ demo 已交付，真实工程待阶段 2 完成后启动）|
| 整体规划 | 欧尼酱拍板，蕾姆酱执行 |

---

## 版本

| 版本 | 日期 | 作者 | 变更 |
|------|------|------|------|
| v1.0 | 2026-06-16 | 蕾姆酱 🩵 | 应欧尼酱要求重写：删 v0.xx 版本号，改 3 大阶段人话版（旧文件保留为 `.legacy`）|
