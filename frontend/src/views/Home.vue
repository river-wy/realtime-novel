<script setup lang="ts">
/**
 * Home 首页（v0.5 接入后端 API）
 *
 * 首屏 hero + 项目列表 + "新启动" 入口
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import * as api from '@/api/projects'
import heroImage from '@/assets/首页-主图.png'

const router = useRouter()
const projectsStore = useProjectsStore()

onMounted(async () => {
  await projectsStore.loadList()
})

/** v0.8.3: 智能跳转 — 未完成 onboard 续接, 已完成跳世界详情 */
function goToProject(p: api.ProjectInfo | string) {
  // 兼容传 id 字符串的旧调用
  if (typeof p === 'string') {
    const project = projectsStore.projects.find((x) => x.id === p)
    if (!project) {
      router.push({ name: 'world', params: { projectId: p } })
      return
    }
    p = project
  }
  if (p.chapter_count > 0) {
    // 有章节, 跳到阅读页第 1 章
    router.push({ name: 'reader', params: { projectId: p.id, chapterNum: 1 } })
  } else if (p.onboarding_step === 4) {
    // v0.8.3: onboard 完成 (Step 4) 但还没生成章节 → 跳世界详情 (有"生成第 1 章"按钮)
    router.push({ name: 'world', params: { projectId: p.id } })
  } else if (p.onboarding_step && p.onboarding_step >= 1) {
    // onboard 进行中 (Step 1-3), 跳到续接点
    router.push({ name: 'onboarding', query: { projectId: p.id, step: String(p.onboarding_step) } })
  } else {
    // 从未进过, 跳到世界详情
    router.push({ name: 'world', params: { projectId: p.id } })
  }
}

function startNewProject() {
  router.push({ name: 'onboarding' })
}

/** v0.8: 探索度辅助函数 */
function explorationIcon(level: string): string {
  return { conservative: '🛡️', standard: '⚖️', wild: '🌌' }[level] || '⚖️'
}
function explorationLabel(level: string): string {
  return { conservative: '保守', standard: '标准', wild: '狂野' }[level] || '标准'
}
function explorationDesc(level: string): string {
  return {
    conservative: '严守用户输入, AI 补充少',
    standard: '平衡, AI 合理补充',
    wild: '大胆发散, 探索不同方向',
  }[level] || ''
}

/** v0.8.3: 项目状态辅助函数 */
function statusIcon(status: string): string {
  return { not_started: '⚪', in_progress: '🟡', completed: '🟢' }[status] || '⚪'
}
function statusLabel(status: string, step: number | null): string {
  if (status === 'completed') return '已完成'
  if (status === 'in_progress' && step) {
    return step >= 3 ? `大纲中 (${step}/5)` : `引导中 (${step}/5)`
  }
  return '未启动'
}
function statusDesc(status: string, step: number | null): string {
  if (status === 'completed') return '可阅读, 可继续生成'
  if (status === 'in_progress' && step) {
    if (step >= 3) return `点击续接 Step ${step} 大纲生成`
    return `点击续接 Step ${step} 启动`
  }
  return '点击继续启动'
}
</script>

<template>
  <div class="home">
    <!-- Hero -->
    <section class="hero fade-in">
      <div class="hero-bg">
        <div class="star"></div>
        <div class="star"></div>
        <div class="star"></div>
        <div class="star"></div>
        <div class="star"></div>
      </div>
      <div class="hero-glow">
        <img :src="heroImage" alt="realtime-novel 主图" class="hero-image" />
      </div>
      <p class="hero-subtitle">实时生成 · 可干预 · 可回档</p>
      <p class="hero-desc">基于 LLM 的小说创作平台。世界树 + 主线 + 人物 + 种子表，让 AI 写你心中的故事。</p>
      <div class="hero-actions">
        <button class="btn btn-primary" @click="startNewProject">✨ 新启动一个世界</button>
        <button v-if="projectsStore.projects.length > 0" class="btn btn-secondary" @click="goToProject(projectsStore.projects[0])">
          打开最近项目
        </button>
      </div>
    </section>

    <!-- 项目列表 -->
    <section class="projects-section">
      <h2 class="section-title">我的世界</h2>
      <div v-if="projectsStore.loading" class="loading">加载中...</div>
      <div v-else-if="projectsStore.projects.length === 0" class="empty">
        <p>还没有世界</p>
        <button class="btn btn-primary" @click="startNewProject">启动第一个世界</button>
      </div>
      <div v-else class="project-grid">
        <article
          v-for="p in projectsStore.projects"
          :key="p.id"
          class="project-card"
          @click="goToProject(p)"
        >
          <div class="card-bg" :style="{ background: `linear-gradient(135deg, var(--color-night-2), var(--color-night-3))` }"></div>
          <div class="card-content">
            <h3 class="card-title">{{ p.name }}</h3>
            <p class="card-meta">
              <span class="palette">{{ p.palette }}</span>
              <!-- v0.8: 探索度徽章 -->
              <span
                class="exploration-badge"
                :class="`exploration-${p.exploration_level || 'standard'}`"
                :title="explorationDesc(p.exploration_level || 'standard')"
              >
                {{ explorationIcon(p.exploration_level || 'standard') }}
                {{ explorationLabel(p.exploration_level || 'standard') }}
              </span>
              <!-- v0.8.3: 状态徽章 -->
              <span
                class="status-badge"
                :class="`status-${p.status || 'not_started'}`"
                :title="statusDesc(p.status || 'not_started', p.onboarding_step)"
              >
                {{ statusIcon(p.status || 'not_started') }}
                {{ statusLabel(p.status || 'not_started', p.onboarding_step) }}
              </span>
              <span class="chapter-count">{{ p.chapter_count }} 章</span>
            </p>
          </div>
        </article>
      </div>
    </section>

    <!-- 特性 -->
    <section class="features">
      <h2 class="section-title">三大特性</h2>
      <div class="feature-grid">
        <div class="feature">
          <div class="feature-icon">⚡</div>
          <h3>实时生成</h3>
          <p>基于 deepseek-v4-pro，60 秒生成一章</p>
        </div>
        <div class="feature">
          <div class="feature-icon">🎭</div>
          <h3>可干预</h3>
          <p>导演 / 演员双模式干预剧情</p>
        </div>
        <div class="feature">
          <div class="feature-icon">⏪</div>
          <h3>可回档</h3>
          <p>任意章节回档，章节 + 基座同步</p>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home {
  padding: var(--space-5) 0;
}

/* Hero */
.hero {
  position: relative;
  text-align: center;
  padding: var(--space-8) var(--space-4);
  background: linear-gradient(180deg, var(--color-night-2) 0%, transparent 100%);
  border-radius: var(--radius-lg);
  overflow: hidden;
  margin-bottom: var(--space-7);
}

.hero-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.star {
  position: absolute;
  width: 4px;
  height: 4px;
  background: var(--color-accent-2);
  border-radius: 50%;
  animation: sparkle 3s ease-in-out infinite;
}
.star:nth-child(1) { top: 20%; left: 15%; animation-delay: 0s; }
.star:nth-child(2) { top: 35%; right: 20%; animation-delay: 0.5s; }
.star:nth-child(3) { top: 60%; left: 25%; animation-delay: 1s; }
.star:nth-child(4) { top: 75%; right: 30%; animation-delay: 1.5s; }
.star:nth-child(5) { top: 45%; left: 50%; animation-delay: 2s; }

.hero-image {
  display: block;
  max-width: 720px;
  width: 100%;
  height: auto;
  margin: 0 auto;
  position: relative;
  border-radius: var(--radius-lg);
  filter: drop-shadow(0 8px 32px rgba(255, 143, 177, 0.25))
          drop-shadow(0 0 24px rgba(139, 92, 246, 0.2));
}

/* 渐变光晕容器：让透明 PNG 融进深紫底 */
.hero-glow {
  position: relative;
  margin: 0 auto var(--space-6);
  padding: 24px 32px;
  border-radius: var(--radius-lg);
  background:
    radial-gradient(ellipse 80% 60% at center,
      rgba(255, 143, 177, 0.22) 0%,
      rgba(139, 92, 246, 0.14) 40%,
      rgba(27, 15, 46, 0) 70%
    );
}

.hero-glow::before {
  content: '';
  position: absolute;
  inset: -8px;
  border-radius: var(--radius-lg);
  background:
    radial-gradient(ellipse 70% 50% at center,
      rgba(255, 143, 177, 0.10) 0%,
      transparent 60%
    );
  z-index: -1;
  filter: blur(8px);
}

.hero-subtitle {
  font-size: var(--text-2xl);
  color: var(--color-accent-1);
  margin-bottom: var(--space-3);
  position: relative;
}

.hero-desc {
  font-size: var(--text-base);
  color: var(--color-text-dim);
  max-width: 600px;
  margin: 0 auto var(--space-6);
  position: relative;
}

.hero-actions {
  display: flex;
  gap: var(--space-4);
  justify-content: center;
  position: relative;
}

.btn {
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-weight: 500;
  transition: all var(--motion-fast) var(--ease-out);
}

.btn-primary {
  background: linear-gradient(135deg, var(--color-accent-1), var(--color-accent-3));
  color: white;
  box-shadow: var(--shadow-glow);
}
.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 32px rgba(255, 143, 177, 0.5);
}

.btn-secondary {
  background: transparent;
  border: 1px solid var(--color-accent-3);
  color: var(--color-accent-3);
}
.btn-secondary:hover {
  background: rgba(139, 92, 246, 0.1);
}

/* Sections */
.section-title {
  font-size: var(--text-2xl);
  margin-bottom: var(--space-5);
  color: var(--color-accent-1);
}

.projects-section,
.features {
  margin-bottom: var(--space-7);
}

.loading,
.empty {
  text-align: center;
  padding: var(--space-6);
  color: var(--color-text-dim);
}

.empty .btn {
  margin-top: var(--space-4);
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}

.project-card {
  position: relative;
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  transition: transform var(--motion-base) var(--ease-out);
  min-height: 160px;
}

.project-card:hover {
  transform: translateY(-4px);
}

.card-bg {
  position: absolute;
  inset: 0;
  opacity: 0.7;
}

.card-content {
  position: relative;
  padding: var(--space-5);
}

.card-title {
  font-size: var(--text-xl);
  margin-bottom: var(--space-3);
  color: var(--color-text);
}

.card-meta {
  display: flex;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-dim);
}

.palette {
  background: rgba(139, 92, 246, 0.2);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

.chapter-count {
  color: var(--color-accent-2);
}

/* v0.8: 探索度徽章 */
.exploration-badge {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.exploration-conservative {
  background: rgba(99, 102, 241, 0.2);   /* 蓝 */
  color: #a5b4fc;
  border: 1px solid rgba(99, 102, 241, 0.4);
}
.exploration-standard {
  background: rgba(139, 92, 246, 0.2);    /* 紫 */
  color: #c4b5fd;
  border: 1px solid rgba(139, 92, 246, 0.4);
}
.exploration-wild {
  background: rgba(236, 72, 153, 0.2);    /* 粉 */
  color: #f9a8d4;
  border: 1px solid rgba(236, 72, 153, 0.4);
}

/* v0.8.3: 状态徽章 (not_started / in_progress / completed) */
.status-badge {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.status-not_started {
  background: rgba(156, 163, 175, 0.2);  /* 灰 */
  color: #d1d5db;
  border: 1px solid rgba(156, 163, 175, 0.4);
}
.status-in_progress {
  background: rgba(251, 191, 36, 0.2);   /* 黄 */
  color: #fde68a;
  border: 1px solid rgba(251, 191, 36, 0.4);
}
.status-completed {
  background: rgba(34, 197, 94, 0.2);    /* 绿 */
  color: #86efac;
  border: 1px solid rgba(34, 197, 94, 0.4);
}

/* Features */
.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-4);
}

.feature {
  text-align: center;
  padding: var(--space-5);
  background: var(--color-night-2);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-night-3);
  transition: all var(--motion-base) var(--ease-out);
}

.feature:hover {
  border-color: var(--color-accent-1);
  transform: translateY(-2px);
}

.feature-icon {
  font-size: 40px;
  margin-bottom: var(--space-3);
}

.feature h3 {
  font-size: var(--text-lg);
  margin-bottom: var(--space-2);
  color: var(--color-accent-1);
}

.feature p {
  font-size: var(--text-sm);
  color: var(--color-text-dim);
  margin: 0;
}
</style>
