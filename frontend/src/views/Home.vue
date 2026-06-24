<script setup lang="ts">
/**
 * Home 首页（v0.5 接入后端 API）
 *
 * 首屏 hero + 项目列表（默认 7 个 + 更多入口）+ "新启动" 入口
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import * as api from '@/api/projects'
import heroImage from '@/assets/首页-主图.png'

const router = useRouter()
const projectsStore = useProjectsStore()

/** 首页最多展示数量 */
const MAX_CARDS = 7

/** 首页展示的项目（最近 MAX_CARDS 个） */
const recentProjects = computed(() => projectsStore.projects.slice(0, MAX_CARDS))
const hasMore = computed(() => projectsStore.projects.length > MAX_CARDS)

onMounted(async () => {
  await projectsStore.loadList()
})

/** v0.8.3: 智能跳转 — 未完成 onboard 续接, 已完成跳世界详情 */
function goToProject(p: api.ProjectInfo | string) {
  if (typeof p === 'string') {
    const project = projectsStore.projects.find((x) => x.id === p)
    if (!project) {
      router.push({ name: 'world', params: { projectId: p } })
      return
    }
    p = project
  }
  if (p.chapter_count > 0) {
    router.push({ name: 'reader', params: { projectId: p.id, chapterNum: 1 } })
  } else if (p.onboarding_step === 4) {
    router.push({ name: 'world', params: { projectId: p.id } })
  } else if (p.onboarding_step && p.onboarding_step >= 1) {
    router.push({ name: 'onboarding', query: { projectId: p.id, step: String(p.onboarding_step) } })
  } else {
    router.push({ name: 'world', params: { projectId: p.id } })
  }
}

function startNewProject() {
  router.push({ name: 'onboarding' })
}

function goToWorldList() {
  router.push({ name: 'world-list' })
}

// ============ 卡片 "..." 删除菜单 ============

const openMenuId = ref<string | null>(null)

function toggleMenu(e: Event, projectId: string) {
  e.stopPropagation()
  openMenuId.value = openMenuId.value === projectId ? null : projectId
}

function closeMenu() {
  openMenuId.value = null
}

const deleting = ref<string | null>(null)

async function handleDelete(e: Event, project: api.ProjectInfo) {
  e.stopPropagation()
  closeMenu()
  if (!confirm(`确定删除「${project.name}」吗？所有章节、世界树、大纲数据将一并删除，无法恢复。`)) return
  deleting.value = project.id
  try {
    await projectsStore.remove(project.id)
  } catch (err: any) {
    alert(`删除失败: ${err.message}`)
  } finally {
    deleting.value = null
  }
}

// 点击外部关闭菜单
function onDocClick() {
  closeMenu()
}
onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))

// ============ 辅助函数 ============

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
      <div class="section-header">
        <h2 class="section-title">我的世界</h2>
        <button v-if="projectsStore.projects.length > 0" class="btn-text" @click="goToWorldList">
          查看全部 ({{ projectsStore.total }}) →
        </button>
      </div>
      <div v-if="projectsStore.loading" class="loading">加载中...</div>
      <div v-else-if="projectsStore.projects.length === 0" class="empty">
        <p>还没有世界</p>
        <button class="btn btn-primary" @click="startNewProject">启动第一个世界</button>
      </div>
      <div v-else class="project-grid">
        <article
          v-for="p in recentProjects"
          :key="p.id"
          class="project-card"
          @click="goToProject(p)"
        >
          <!-- v0.9: 左图右字布局 -->
          <div class="card-inner">
            <!-- 左：封面缩略图 -->
            <div
              class="card-thumb"
              :class="p.cover_image_url ? 'card-thumb-image' : 'card-thumb-placeholder'"
              :style="p.cover_image_url ? { backgroundImage: `url(${p.cover_image_url})` } : {}"
            >
              <span v-if="!p.cover_image_url" class="card-thumb-icon">📖</span>
            </div>
            <!-- 右：标题 + 标签 + 章节 -->
            <div class="card-content">
              <h3 class="card-title">{{ p.name }}</h3>
              <div class="card-meta">
                <span class="palette">{{ p.palette }}</span>
                <span
                  class="exploration-badge"
                  :class="`exploration-${p.exploration_level || 'standard'}`"
                  :title="explorationDesc(p.exploration_level || 'standard')"
                >
                  {{ explorationIcon(p.exploration_level || 'standard') }}
                  {{ explorationLabel(p.exploration_level || 'standard') }}
                </span>
                <span
                  class="status-badge"
                  :class="`status-${p.status || 'not_started'}`"
                  :title="statusDesc(p.status || 'not_started', p.onboarding_step)"
                >
                  {{ statusIcon(p.status || 'not_started') }}
                  {{ statusLabel(p.status || 'not_started', p.onboarding_step) }}
                </span>
              </div>
              <div class="card-chapter-count">{{ p.chapter_count }} 章</div>
            </div>
          </div>
          <!-- "..." 操作菜单 -->
          <div class="card-menu" @click="toggleMenu($event, p.id)">
            <span class="card-menu-icon">⋯</span>
          </div>
          <div
            v-if="openMenuId === p.id"
            class="card-menu-dropdown"
            @click.stop
          >
            <button
              class="menu-item menu-danger"
              :disabled="deleting === p.id"
              @click="handleDelete($event, p)"
            >
              {{ deleting === p.id ? '删除中...' : '🗑 删除' }}
            </button>
          </div>
        </article>

        <!-- "更多" 卡片 -->
        <article v-if="hasMore" class="project-card more-card" @click="goToWorldList">
          <div class="card-bg" :style="{ background: `linear-gradient(135deg, var(--color-night-1), var(--color-night-2))` }"></div>
          <div class="card-content more-content">
            <span class="more-icon">📚</span>
            <span class="more-text">查看全部<br>{{ projectsStore.total }} 个世界</span>
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

/* Section header */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-5);
}

.section-title {
  font-size: var(--text-2xl);
  color: var(--color-accent-1);
  margin: 0;
}

.btn-text {
  background: none;
  border: none;
  color: var(--color-accent-3);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: opacity var(--motion-fast);
}
.btn-text:hover {
  opacity: 0.7;
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
  background: var(--color-night-2);
  border: 1px solid var(--color-night-3);
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  transition: all var(--motion-base) var(--ease-out);
}
.project-card:hover {
  transform: translateY(-3px);
  border-color: var(--color-accent-3);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

/* v0.9: 左图右字内层 */
.card-inner {
  display: flex;
  gap: 0;
  align-items: stretch;
  min-height: 100px;
}

/* 左：封面缩略图 */
.card-thumb {
  width: 100px;
  flex-shrink: 0;
  background-size: cover;
  background-position: center;
  position: relative;
  overflow: hidden;
}
.card-thumb-image {
  /* 有图直接显示背景图 */
}
.card-thumb-placeholder {
  background: linear-gradient(160deg, var(--color-night-1), var(--color-night-3));
  display: flex;
  align-items: center;
  justify-content: center;
}
.card-thumb-icon {
  font-size: 36px;
  opacity: 0.35;
}

/* 右：内容区 */
.card-content {
  flex: 1;
  padding: var(--space-4);
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.card-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: var(--space-2);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-bottom: var(--space-2);
}

.palette {
  background: rgba(139, 92, 246, 0.2);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
}

.card-chapter-count {
  font-size: var(--text-xs);
  color: var(--color-accent-2);
  font-weight: 500;
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
  background: rgba(99, 102, 241, 0.2);
  color: #a5b4fc;
  border: 1px solid rgba(99, 102, 241, 0.4);
}
.exploration-standard {
  background: rgba(139, 92, 246, 0.2);
  color: #c4b5fd;
  border: 1px solid rgba(139, 92, 246, 0.4);
}
.exploration-wild {
  background: rgba(236, 72, 153, 0.2);
  color: #f9a8d4;
  border: 1px solid rgba(236, 72, 153, 0.4);
}

/* v0.8.3: 状态徽章 */
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
  background: rgba(156, 163, 175, 0.2);
  color: #d1d5db;
  border: 1px solid rgba(156, 163, 175, 0.4);
}
.status-in_progress {
  background: rgba(251, 191, 36, 0.2);
  color: #fde68a;
  border: 1px solid rgba(251, 191, 36, 0.4);
}
.status-completed {
  background: rgba(34, 197, 94, 0.2);
  color: #86efac;
  border: 1px solid rgba(34, 197, 94, 0.4);
}

/* ============ 卡片 "..." 菜单 ============ */
.card-menu {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  cursor: pointer;
  z-index: 2;
  opacity: 0;
  transition: opacity var(--motion-fast);
  background: rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(4px);
}
.project-card:hover .card-menu {
  opacity: 1;
}
.card-menu-icon {
  font-size: 20px;
  color: var(--color-text-dim);
  line-height: 1;
  transform: rotate(90deg);
  letter-spacing: -2px;
}

.card-menu-dropdown {
  position: absolute;
  top: 42px;
  right: 8px;
  z-index: 10;
  background: var(--color-night-1);
  border: 1px solid var(--color-night-3);
  border-radius: var(--radius-sm);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  min-width: 120px;
  overflow: hidden;
}

.menu-item {
  display: block;
  width: 100%;
  padding: var(--space-2) var(--space-4);
  background: none;
  border: none;
  text-align: left;
  font-size: var(--text-sm);
  color: var(--color-text);
  cursor: pointer;
  transition: background var(--motion-fast);
}
.menu-item:hover:not(:disabled) {
  background: var(--color-night-2);
}
.menu-item:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.menu-danger {
  color: #f87171;
}
.menu-danger:hover:not(:disabled) {
  background: rgba(248, 113, 113, 0.1);
}

/* ============ "更多" 卡片 ============ */
.more-card {
  display: flex;
  align-items: center;
  justify-content: center;
}
.more-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  text-align: center;
  height: 100%;
  min-height: 120px;
}
.more-icon {
  font-size: 36px;
}
.more-text {
  font-size: var(--text-sm);
  color: var(--color-accent-3);
  line-height: 1.5;
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
