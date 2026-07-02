# 前端样式体系（Styling）

> **元信息**
> - 日期：2026-07-02
> - 版本：v0.9.6
> - Commit：e717e5b
> - 项目：realtime-novel
> - 适用范围：frontend 全部 Vue 3 组件

---

## 1. 设计 token 体系概览

realtime-novel 前端样式严格基于 **CSS Variables（Custom Properties）** 构建。设计 token 集中在 `frontend/src/styles/tokens.css` 一个文件中定义，组件只允许消费 token，**不允许硬编码颜色、间距、字号等值**。

### 1.1 主题名称

**月光樱花 · 琉璃宫**（代码注释 `tokens.css:1`）

- 主色：月光下的樱花 `#120a26`
- 强调色系：樱粉 `#FF8FB1` / 月光金 `#FFC857` / 星辉紫 `#8B5CF6`
- 风格：深色玻璃拟态（Glassmorphism）+ 樱粉/星辉紫双色光晕

### 1.2 加载顺序

样式按以下顺序在 `frontend/src/main.ts`（或根入口）注入：

```
1. tokens.css   ← 设计变量
2. base.css     ← 全局 reset + 基础样式
3. animations.css ← 关键帧动画
4. 组件 scoped 样式
```

### 1.3 Token 分组结构

| 分组 | 数量 | 说明 |
|------|------|------|
| 背景色 | 4 | 深空 4 层级 |
| 文字色 | 4 | 主/次/弱/反白 |
| 强调色 | 3 | 樱粉/月光金/星辉紫 + 配套 glow |
| 状态色 | 4 | success/warning/error/info |
| 玻璃表面 | 6 | bg/border/blur 三态 |
| 光晕 | 4 | 樱粉/紫/月/强 |
| 阴影 | 4 | sm/md/lg/card |
| 间距 | 8 | 4px 基准，1~8 |
| 圆角 | 5 | sm/md/lg/xl/full |
| 字体 | 4 | display/body/reader/mono |
| 字号 | 8 | xs~4xl |
| 动效曲线 | 4 | spring/out/in/bounce |
| 动效时长 | 4 | fast/base/slow/slower |
| 兼容映射 | 13 | 旧变量名 → 新 token |

---

## 2. tokens.css 完整变量表

> 文件位置：`frontend/src/styles/tokens.css`
> 读取方式：`:root` 选择器定义，所有变量在全局 CSS 作用域内可用

### 2.1 背景色（月光夜空 4 层级）

| 变量 | 值 | 用途 |
|------|------|------|
| `--color-bg-deep` | `#0a0617` | 最底层（页面/全屏背景） |
| `--color-bg-base` | `#120a26` | 基础层（body 默认） |
| `--color-bg-surface` | `#1B1035` | 表面层（卡片底色） |
| `--color-bg-elevated` | `#2A1B4A` | 抬起层（弹窗/输入框） |

> 出处：`tokens.css:9-12`

### 2.2 文字色（4 级）

| 变量 | 值 | 用途 |
|------|------|------|
| `--color-text-primary` | `#F5F0FF` | 主文字（标题/正文） |
| `--color-text-secondary` | `#C4B8E0` | 次文字（说明/辅助） |
| `--color-text-tertiary` | `#8A7FB5` | 弱文字（占位/禁用） |
| `--color-text-on-accent` | `#1B0F2E` | 反白文字（强调色按钮上的字） |

> 出处：`tokens.css:15-18`

### 2.3 强调色（樱花月光系）

| 变量 | 值 | 用途 |
|------|------|------|
| `--color-sakura` | `#FF8FB1` | 樱粉主强调（链接/激活态/CTA） |
| `--color-sakura-light` | `#FFB3CC` | 樱粉淡色（hover/disabled） |
| `--color-sakura-glow` | `rgba(255,143,177,0.25)` | 樱粉光晕底层 |
| `--color-moon` | `#FFC857` | 月光金（次强调/通知点） |
| `--color-moon-glow` | `rgba(255,200,87,0.25)` | 月光金光晕 |
| `--color-violet` | `#8B5CF6` | 星辉紫（图表/装饰/进度条） |
| `--color-violet-glow` | `rgba(139,92,246,0.25)` | 星辉紫光晕 |

> 出处：`tokens.css:21-27`

### 2.4 状态色

| 变量 | 值 | 用途 |
|------|------|------|
| `--color-success` | `#4ADE80` | 成功（toast/对勾） |
| `--color-warning` | `#FBBF24` | 警告（提醒） |
| `--color-error` | `#F87171` | 错误（toast/必填提示） |
| `--color-info` | `#60A5FA` | 信息（toast/链接） |

> 出处：`tokens.css:30-33`

### 2.5 玻璃表面（Glassmorphism）

| 变量 | 值 | 用途 |
|------|------|------|
| `--glass-bg` | `rgba(255,255,255,0.04)` | 玻璃底色（默认） |
| `--glass-bg-hover` | `rgba(255,255,255,0.08)` | 玻璃底色（hover） |
| `--glass-bg-active` | `rgba(255,255,255,0.12)` | 玻璃底色（active） |
| `--glass-border` | `rgba(255,255,255,0.08)` | 玻璃边框 |
| `--glass-border-hover` | `rgba(255,143,177,0.3)` | 玻璃边框（hover，樱粉） |
| `--glass-blur` | `20px` | 背景模糊半径 |

> 出处：`tokens.css:36-41`

### 2.6 光晕（Glow）

| 变量 | 值 | 用途 |
|------|------|------|
| `--glow-sakura` | `0 0 24px rgba(255,143,177,0.3)` | 樱粉辉光 |
| `--glow-violet` | `0 0 24px rgba(139,92,246,0.3)` | 紫光辉光 |
| `--glow-moon` | `0 0 16px rgba(255,200,87,0.35)` | 月光金辉光 |
| `--glow-strong` | `0 0 48px rgba(255,143,177,0.4), 0 0 24px rgba(139,92,246,0.3)` | 复合强光（hero/聚焦） |

> 出处：`tokens.css:44-47`

### 2.7 阴影

| 变量 | 值 | 用途 |
|------|------|------|
| `--shadow-sm` | `0 2px 8px rgba(0,0,0,0.2)` | 微阴影（按钮） |
| `--shadow-md` | `0 8px 24px rgba(0,0,0,0.3)` | 中阴影（卡片） |
| `--shadow-lg` | `0 16px 48px rgba(0,0,0,0.4)` | 大阴影（弹窗） |
| `--shadow-card` | `0 4px 20px rgba(0,0,0,0.25)` | 卡片标准阴影 |

> 出处：`tokens.css:50-53`

### 2.8 间距（4px 基准 8 级）

| 变量 | 值 | 用途 |
|------|------|------|
| `--space-1` | `4px` | 微间距（icon 边距） |
| `--space-2` | `8px` | 小间距（行内） |
| `--space-3` | `12px` | 元素内边距 |
| `--space-4` | `16px` | 标准间距（默认） |
| `--space-5` | `24px` | 段落间距 |
| `--space-6` | `32px` | 区块间距 |
| `--space-7` | `48px` | 大区块间距 |
| `--space-8` | `64px` | 页面级间距 |

> 出处：`tokens.css:56-63`

### 2.9 圆角

| 变量 | 值 | 用途 |
|------|------|------|
| `--radius-sm` | `8px` | 小圆角（输入框/按钮） |
| `--radius-md` | `14px` | 中圆角（卡片/弹窗） |
| `--radius-lg` | `20px` | 大圆角（容器/区块） |
| `--radius-xl` | `28px` | 极大圆角（特殊卡片） |
| `--radius-full` | `9999px` | 全圆（圆形头像/Pill 按钮） |

> 出处：`tokens.css:66-70`

### 2.10 字体

| 变量 | 值 | 用途 |
|------|------|------|
| `--font-display` | `'Noto Serif SC', 'Cormorant Garamond', serif` | 标题字体（衬线/有分量） |
| `--font-body` | `'Plus Jakarta Sans', 'Noto Sans SC', sans-serif` | 正文字体（UI 全局） |
| `--font-reader` | `'Noto Serif SC', 'Libre Baskerville', serif` | 阅读模式字体（章节正文） |
| `--font-mono` | `'JetBrains Mono', monospace` | 等宽（代码片段/调试） |

> 出处：`tokens.css:73-76`

**字体加载方式**（`index.html:7-9`）：从 Google Fonts 预连接 + 一次性加载 5 个字体族（Noto Serif SC / Plus Jakarta Sans / Noto Sans SC / JetBrains Mono / Zen Maru Gothic）。

### 2.11 字号

| 变量 | 值 | 用途 |
|------|------|------|
| `--text-xs` | `12px` | 微文字（角标/版权） |
| `--text-sm` | `14px` | 小文字（次要信息） |
| `--text-base` | `16px` | 基础（正文默认） |
| `--text-lg` | `18px` | 较大（强调段落） |
| `--text-xl` | `20px` | 小标题 |
| `--text-2xl` | `24px` | 中标题 |
| `--text-3xl` | `32px` | 大标题 |
| `--text-4xl` | `48px` | hero/超大字 |

> 出处：`tokens.css:79-86`

### 2.12 动效曲线（4 种 ease）

| 变量 | 值 | 用途 |
|------|------|------|
| `--ease-spring` | `cubic-bezier(0.16, 1, 0.3, 1)` | 弹性（弹入/抽屉） |
| `--ease-out` | `cubic-bezier(0, 0, 0.2, 1)` | 缓出（标准淡入） |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | 缓入（淡出/消失） |
| `--ease-bounce` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | 回弹（按钮按下） |

> 出处：`tokens.css:89-92`

### 2.13 动效时长

| 变量 | 值 | 用途 |
|------|------|------|
| `--dur-fast` | `150ms` | 微动效（hover/颜色变化） |
| `--dur-base` | `250ms` | 标准动效（淡入/淡出） |
| `--dur-slow` | `400ms` | 慢动效（抽屉/弹窗） |
| `--dur-slower` | `600ms` | 极慢动效（页面切换） |

> 出处：`tokens.css:93-96`

### 2.14 兼容映射（旧变量名 → 新 token）

> 出处：`tokens.css:99-115`

为平滑迁移，tokens.css 末尾定义了 14 个**兼容别名**：旧版变量名 → 新版 token。

| 旧变量 | 映射到 |
|--------|--------|
| `--color-night-1` | `--color-bg-surface` |
| `--color-night-2` | `--color-bg-elevated` |
| `--color-night-3` | `--color-bg-overlay`（或 `#3D2A66` 兜底） |
| `--color-text` / `--color-text-dim` / `--color-text-faint` | `--color-text-primary/secondary/tertiary` |
| `--color-accent-1/2/3` | `--color-sakura/moon/violet` |
| `--shadow-glow` / `--shadow-glow-strong` | `--glow-sakura` / `--glow-strong` |
| `--motion-fast/base/slow` | `--dur-fast/base/slow` |
| `--radius-full` | `9999px`（已在 §2.9 声明，此处重复） |

> ⚠️ **新代码应直接使用新 token**，别名仅供旧组件平滑过渡。

---

## 3. base.css 全局基础样式

> 文件位置：`frontend/src/styles/base.css`

### 3.1 Reset

- 通用 box-sizing：`*, *::before, *::after { box-sizing: border-box; }`（`base.css:3-5`）
- html/body 去除默认 margin/padding（`base.css:7-9`）

### 3.2 Body 基础

```css
html, body {
  font-family: var(--font-body);       /* UI 全局字体 */
  font-size: var(--text-base);         /* 16px */
  line-height: 1.6;
  color: var(--color-text-primary);
  background: var(--color-bg-base);    /* #120a26 月光紫 */
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  height: 100%;
}
```

> 出处：`base.css:7-19`

### 3.3 月光流动光斑（body 伪元素）

body 上挂两个 `::before` / `::after` 伪元素作为**环境光斑**，随时间漂移：

| 伪元素 | 位置 | 颜色 | 动画 | 时长 |
|--------|------|------|------|------|
| `body::before` | 左上 (-10%, -10%) | 樱粉 `rgba(255,143,177,0.06)` | `drift1` | 28s alternate infinite |
| `body::after` | 右下 (-10%, -10%) | 紫 `rgba(139,92,246,0.05)` | `drift2` | 32s alternate infinite |

- z-index: 0，pointer-events: none，不影响交互
- drift1 终点位移 (200px, 150px)，drift2 终点位移 (-180px, -120px)

> 出处：`base.css:21-50`

### 3.4 标题 / 段落 / 链接

- h1-h6：`font-family: var(--font-display)`，weight 600，line-height 1.3（`base.css:55-60`）
- p：默认 margin-bottom `var(--space-4)`（`base.css:62-64`）
- a：颜色 `--color-sakura`，hover 变 `--color-moon`，过渡 `--dur-fast --ease-out`（`base.css:66-72`）

### 3.5 按钮 / 表单元素

- button：清除 `border` / `background`，继承字体和颜色（`base.css:74-79`）
- input/textarea/select：
  - 背景 `--color-bg-elevated`
  - 边框 `1px solid --glass-border`
  - 圆角 `--radius-md`
  - 内边距 `var(--space-3) var(--space-4)`
  - focus 边框变 `--color-sakura`（`base.css:81-95`）

### 3.6 选区颜色

```css
::selection {
  background: rgba(255, 143, 177, 0.3);  /* 樱粉淡透明 */
}
```

> 出处：`base.css:97-99`

### 3.7 滚动条

| 状态 | 样式 |
|------|------|
| 轨道 | 透明（`base.css:103-105`） |
| 滑块 | `--color-bg-elevated`，圆角 `--radius-full`（`base.css:106-109`） |
| 滑块 hover | `--color-violet`（`base.css:110-112`） |
| 尺寸 | width 8px，height 8px（`base.css:101-102`） |

### 3.8 无障碍：reduced-motion

```css
@media (prefers-reduced-motion: reduce) {
  body::before, body::after {
    animation: none !important;
  }
  .petal-container {
    display: none !important;
  }
}
```

> 出处：`base.css:115-122`
> 操作系统设置"减少动效"时，自动停用月光光斑和花瓣装饰。

---

## 4. animations.css 关键帧动画

> 文件位置：`frontend/src/styles/animations.css`

### 4.1 淡入类（5 种方向）

| 关键帧 | 位移 | 用途 |
|--------|------|------|
| `fadeIn` | Y +8px → 0 | 通用淡入（卡片/列表） |
| `fadeInDown` | Y -12px → 0 | 顶部下拉（通知/Toast） |
| `fadeInUp` | Y +16px → 0 | 底部上推（操作栏） |
| `fadeInLeft` | X -20px → 0 | 从左进入（侧栏） |
| `fadeInRight` | X +20px → 0 | 从右进入（侧栏） |

> 出处：`animations.css:3-23`

### 4.2 滑入类

| 关键帧 | 用途 |
|--------|------|
| `slideInRight` | 从右滑入（抽屉/侧栏，X +20px → 0） |
| `slideInLeft` | 从左滑入（抽屉/侧栏，X -20px → 0） |

> 出处：`animations.css:25-33`

### 4.3 装饰/动效类

| 关键帧 | 效果 | 用途 |
|--------|------|------|
| `sparkle` | 0.3→1→0.3 透明度 + scale 0.8→1.2 | 星点闪烁（loading/装饰） |
| `glow` | 樱粉 box-shadow 0.2→0.6 脉动 | 强调按钮/激活态 |
| `drift` | 0→(20,-10)→0 自由漂移 | 装饰元素 |
| `pulse` | opacity 1→0.6→1 | 占位符/呼吸 |
| `spin` | rotate 0→360deg | 加载 spinner |
| `blink` | opacity 0 at 50% | 打字光标 |
| `thinking-pulse` | opacity 0.5 at 50% | AI 思考中指示器 |
| `shimmer` | background-position 200%→-200% | skeleton 骨架屏 |

> 出处：`animations.css:35-69`

### 4.4 专用类

| 关键帧 | 用途 |
|--------|------|
| `petal-fall` | 樱花花瓣下落（Y 0→110vh + 360°旋转） |
| `indicator-slide` | 指示器 scaleX 0→1（Tab 切换/进度条） |
| `menuIn` | 菜单 scale 0.95→1 + opacity 0→1 |
| `dialogIn` | 对话框 scale 0.92→1 + opacity 0→1 |
| `cardIn` | 卡片 Y +12px→0 |
| `bannerIn` | 横幅 scale 1.05→1 + opacity 0→1 |

> 出处：`animations.css:71-103`

### 4.5 工具类

| 类名 | 行为 |
|------|------|
| `.fade-in` | 应用 `fadeIn` 动画，时长 `--dur-base`，曲线 `--ease-out` |
| `.glow` | 应用 `glow` 动画，2s 无限循环 |
| `.sparkle` | 应用 `sparkle` 动画，2s 无限循环 |
| `.skeleton-shimmer` | 骨架屏渐变背景，1.8s 无限循环 |

> 出处：`animations.css:106-120`

---

## 5. 样式约定

### 5.1 Scoped 优先

**所有 Vue 组件的 `<style>` 必须带 `scoped`**。例外：根入口 `App.vue` / `main.ts` 的全局样式；第三方库覆写用 `:deep()` 穿透。

### 5.2 CSS 变量强制

**禁止硬编码颜色、间距、字号**。所有取值必须走 token。

```vue
<!-- ❌ 硬编码 -->
.btn { background: #FF8FB1; padding: 16px; }

<!-- ✅ token -->
.btn { background: var(--color-sakura); padding: var(--space-4); }
```

### 5.3 响应式断点

| 断点 | 场景 |
|------|------|
| `@media (max-width: 1024px)` | 平板（窄屏布局） |
| `@media (max-width: 640px)` | 手机（单列） |

### 5.4 过渡统一

```css
.element {
  transition:
    background var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    transform var(--dur-base) var(--ease-spring);
}
```

**不要写死** `transition: all 0.2s ease`。

### 5.5 玻璃拟态

```css
.glass {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border-radius: var(--radius-md);
}
```

### 5.6 z-index 分层

| 层级 | 范围 | 用途 |
|------|------|------|
| 背景 | 0 | body 伪元素 |
| 内容 | 1~10 | 卡片 |
| 浮层 | 100~999 | 菜单/Tooltip |
| 弹窗 | 1000~9999 | Modal/Drawer |
| Toast | 10000+ | 全局通知 |

---

## 6. 主题切换

### 6.1 当前状态

**v0.9.6 仅深色主题**。tokens.css 只在 `:root` 定义一组 token，**没有** `[data-theme="light"]` 备用主题。

### 6.2 主题色板定位

| 角色 | 颜色 | 含义 |
|------|------|------|
| 樱粉 | `#FF8FB1` | 主品牌 / 创作 |
| 月光金 | `#FFC857` | 通知 / 提示 |
| 星辉紫 | `#8B5CF6` | 数据 / 进度 |
| 深空紫 | `#120a26` | 主背景 |
| 玻璃白 | `rgba(255,255,255,0.04)` | 表面 / 浮层 |

**核心隐喻**：夜色 + 樱花 + 月光，营造"夜读创作"沉浸感。

### 6.3 预留扩展点

如未来要加浅色主题，建议在 `tokens.css` 末尾追加：

```css
[data-theme="light"] {
  --color-bg-base: #FAF8FF;
  --color-bg-surface: #FFFFFF;
  --color-bg-elevated: #F0EAFB;
  --color-text-primary: #1B0F2E;
  --color-text-secondary: #4A3A6E;
  --glass-bg: rgba(255, 255, 255, 0.7);
  --glass-border: rgba(0, 0, 0, 0.08);
}
```

切换方式：`document.documentElement.dataset.theme = 'light'`，配合 `useTheme` composable 持久化到 localStorage。

---

## 7. 样式文件清单

| 文件 | 行数级别 | 作用 |
|------|---------|------|
| `frontend/src/styles/tokens.css` | 116 | 设计 token 定义（唯一来源） |
| `frontend/src/styles/base.css` | 122 | Reset + body + 表单 + 滚动条 |
| `frontend/src/styles/animations.css` | 120 | 18 个关键帧 + 4 个工具类 |

**所有组件 scoped 样式** 应通过 `var(--token-name)` 消费，不重复定义颜色/间距/字号。

---

## 8. 检查清单

写组件样式时必须满足：

- [ ] `<style scoped>` 标记
- [ ] 颜色 / 间距 / 字号 / 圆角 / 动效全部走 `var(--token-*)`
- [ ] 阴影用 `var(--shadow-*)` 或 `var(--glow-*)`
- [ ] `transition` 不写 `all`，要明确属性
- [ ] 玻璃面板用 `var(--glass-*)` + `backdrop-filter: blur(var(--glass-blur))`
- [ ] 不重复定义 token（需要新值先在 tokens.css 加）
- [ ] 响应式断点统一 `@media (max-width: 1024px)` / `640px`
