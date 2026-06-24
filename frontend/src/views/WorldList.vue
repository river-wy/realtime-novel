<script setup lang="ts">
/**
 * WorldList 全量世界列表页
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import * as api from '@/api/projects'

const router = useRouter()
const projectsStore = useProjectsStore()

onMounted(async () => {
  await projectsStore.loadList(200)
})

function goToProject(p: api.ProjectInfo) {
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

// ============ 删除菜单 ============
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

function onDocClick() { closeMenu() }
onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))

// ============ 辅助函数 ============
function explorationIcon(level: string): string {
  return { conservative: '🛡️', standard: '⚖️', wild: '🌌' }[level] || '⚖️'
}
function explorationLabel(level: string): string {
  return { conservative: '保守', standard: '标准', wild: '狂野' }[level] || '标准'
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
</script>

<template>
  <div class="world-list">
    <header class="list-header">
      <button class="back-btn" @click="router.push({ name: 'home' })">←</button>
      <h1>全部世界</h1>
      <span class="count">{{ projectsStore.total }}</span>
    </header>

    <div v-if="projectsStore.loading" class="loading">加载中...</div>
    <div v-else-if="projectsStore.projects.length === 0" class="empty">
      <p>还没有世界</p>
      <button class="btn btn-primary" @click="router.push({ name: 'onboarding' })">启动第一个世界</button>
    </div>
    <div v-else class="project-grid">
      <article
        v-for="p in projectsStore.projects"
        :key="p.id"
        class="project-card"
        @click="goToProject(p)"
      >
        <!-- v0.9: 封面图背景（有图用图，无图用渐变占位） -->
        <div
          class="card-bg"
          :class="p.cover_image_url ? 'card-bg-image' : 'card-bg-placeholder'"
          :style="p.cover_image_url
            ? { backgroundImage: `url(${p.cover_image_url})` }
            : {}"
        >
          <span v-if="!p.cover_image_url" class="card-bg-placeholder-icon">📖</span>
        </div>
        <div class="card-content">
          <h3 class="card-title">{{ p.name }}</h3>
          <p class="card-meta">
            <span class="palette">{{ p.palette }}</span>
            <span
              class="exploration-badge"
              :class="`exploration-${p.exploration_level || 'standard'}`"
            >
              {{ explorationIcon(p.exploration_level || 'standard') }}
              {{ explorationLabel(p.exploration_level || 'standard') }}
            </span>
            <span
              class="status-badge"
              :class="`status-${p.status || 'not_started'}`"
            >
              {{ statusIcon(p.status || 'not_started') }}
              {{ statusLabel(p.status || 'not_started', p.onboarding_step) }}
            </span>
            <span class="chapter-count">{{ p.chapter_count }} 章</span>
          </p>
        </div>
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
    </div>
  </div>
</template>

<style scoped>
.world-list {
  padding: var(--space-5) 0;
  max-width: 1200px;
  margin: 0 auto;
}

.list-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-6);
}
.list-header h1 {
  font-size: var(--text-2xl);
  color: var(--color-accent-1);
  margin: 0;
}
.back-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--color-night-2);
  border: 1px solid var(--color-night-3);
  color: var(--color-text);
  cursor: pointer;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.back-btn:hover {
  background: var(--color-night-3);
}
.count {
  font-size: var(--text-sm);
  color: var(--color-text-dim);
  background: var(--color-night-2);
  padding: 2px 10px;
  border-radius: var(--radius-full);
}

.loading, .empty {
  text-align: center;
  padding: var(--space-6);
  color: var(--color-text-dim);
}
.empty .btn {
  margin-top: var(--space-4);
}
.btn {
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-weight: 500;
  cursor: pointer;
}
.btn-primary {
  background: linear-gradient(135deg, var(--color-accent-1), var(--color-accent-3));
  color: white;
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
  position: relative;
}
.project-card:hover {
  transform: translateY(-3px);
  border-color: var(--color-accent-3);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

/* v0.9: 左图右字 */
.card-inner {
  display: flex;
  align-items: stretch;
  min-height: 100px;
}
.card-thumb {
  width: 100px;
  flex-shrink: 0;
  background-size: cover;
  background-position: center;
  position: relative;
  overflow: hidden;
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

.exploration-badge, .status-badge {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.exploration-conservative { background: rgba(99,102,241,.2); color: #a5b4fc; border: 1px solid rgba(99,102,241,.4); }
.exploration-standard { background: rgba(139,92,246,.2); color: #c4b5fd; border: 1px solid rgba(139,92,246,.4); }
.exploration-wild { background: rgba(236,72,153,.2); color: #f9a8d4; border: 1px solid rgba(236,72,153,.4); }
.status-not_started { background: rgba(156,163,175,.2); color: #d1d5db; border: 1px solid rgba(156,163,175,.4); }
.status-in_progress { background: rgba(251,191,36,.2); color: #fde68a; border: 1px solid rgba(251,191,36,.4); }
.status-completed { background: rgba(34,197,94,.2); color: #86efac; border: 1px solid rgba(34,197,94,.4); }

/* "..." 菜单 */
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
.menu-item:hover:not(:disabled) { background: var(--color-night-2); }
.menu-item:disabled { opacity: 0.5; cursor: not-allowed; }
.menu-danger { color: #f87171; }
.menu-danger:hover:not(:disabled) { background: rgba(248, 113, 113, 0.1); }
</style>
