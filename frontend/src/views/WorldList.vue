<script setup lang="ts">
/**
 * WorldList 全量世界列表页 · 琉璃宫升级版
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

function goToReader(p: api.ProjectInfo) {
  if (p.chapter_count > 0) {
    router.push({ name: 'reader', params: { projectId: p.id, chapterNum: 1 } })
  }
}

function goToWorld(p: api.ProjectInfo) {
  router.push({ name: 'world', params: { projectId: p.id } })
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
  return { conservative: 'shield', standard: 'scales', wild: 'planet' }[level] || 'scales'
}
function explorationLabel(level: string): string {
  return { conservative: '保守', standard: '标准', wild: '狂野' }[level] || '标准'
}
function statusIcon(status: string): string {
  return { not_started: 'circle', in_progress: 'circle-half', completed: 'check-circle' }[status] || 'circle'
}
function statusLabel(status: string): string {
  if (status === 'completed') return '已完成'
  if (status === 'in_progress') return '进行中'
  return '未启动'
}
</script>

<template>
  <div class="world-list">
    <header class="list-header">
      <button class="back-btn" @click="router.push({ name: 'home' })">
        <i class="ph ph-arrow-left"></i>
      </button>
      <h1>我的世界</h1>
      <span class="count">{{ projectsStore.total }}</span>
    </header>

    <!-- 加载骨架屏 -->
    <div v-if="projectsStore.loading" class="skeleton-grid">
      <div v-for="i in 3" :key="i" class="skeleton-card">
        <div class="skeleton-inner">
          <div class="skeleton-thumb"></div>
          <div class="skeleton-body">
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="projectsStore.projects.length === 0" class="empty">
      <i class="ph ph-book-open empty-icon"></i>
      <p>还没有世界</p>
      <button class="btn btn-primary" @click="router.push({ name: 'home' })">去首页对话启动</button>
    </div>

    <!-- 项目卡片网格 -->
    <div v-else class="project-grid">
      <article
        v-for="(p, i) in projectsStore.projects"
        :key="p.id"
        class="project-card"
        :style="{ animationDelay: `${i * 40}ms` }"
        @click="p.chapter_count > 0 ? goToReader(p) : goToWorld(p)"
      >
        <div class="card-inner">
          <!-- 封面缩略图 -->
          <div
            class="card-thumb"
            :class="p.cover_image_url ? 'card-thumb-image' : 'card-thumb-placeholder'"
            :style="p.cover_image_url ? { backgroundImage: `url(${p.cover_image_url})` } : {}"
          >
            <i v-if="!p.cover_image_url" class="ph ph-book-open thumb-icon"></i>
          </div>
          <!-- 内容 -->
          <div class="card-content">
            <h3 class="card-title" :title="p.name">{{ p.name }}</h3>
            <div class="card-meta">
              <span class="palette">{{ p.palette }}</span>
              <span class="badge" :class="`exploration-${p.exploration_level || 'standard'}`">
                <i :class="`ph ph-${explorationIcon(p.exploration_level || 'standard')}`"></i>
                {{ explorationLabel(p.exploration_level || 'standard') }}
              </span>
              <span class="badge" :class="`status-${p.status || 'not_started'}`">
                <i :class="`ph ph-${statusIcon(p.status || 'not_started')}`"></i>
                {{ statusLabel(p.status || 'not_started') }}
              </span>
            </div>
            <div class="card-chapter-count">{{ p.chapter_count }} 章</div>
          </div>
        </div>
        <!-- 操作按钮 -->
        <div class="card-actions">
          <button class="btn-view" @click.stop="goToWorld(p)">
            <i class="ph ph-eye"></i>查看
          </button>
          <button
            class="btn-read"
            :disabled="p.chapter_count === 0"
            @click.stop="goToReader(p)"
          >
            <i class="ph ph-book-open"></i>立即阅读
          </button>
        </div>
        <!-- "..." 菜单 -->
        <div class="card-menu" @click="toggleMenu($event, p.id)">
          <i class="ph ph-dots-three-vertical"></i>
        </div>
        <div v-if="openMenuId === p.id" class="card-menu-dropdown" @click.stop>
          <button
            class="menu-item menu-danger"
            :disabled="deleting === p.id"
            @click="handleDelete($event, p)"
          >
            <i class="ph ph-trash"></i>
            {{ deleting === p.id ? '删除中...' : '删除' }}
          </button>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.world-list {
  padding: var(--space-5);
  max-width: 1200px;
  margin: 0 auto;
}

.list-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-6);
  animation: fadeInDown 300ms var(--ease-spring);
}
.list-header h1 {
  font-family: var(--font-display);
  font-size: var(--text-2xl);
  color: var(--color-sakura);
  margin: 0;
}
.back-btn {
  width: 36px; height: 36px;
  border-radius: 50%;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--color-text-primary);
  display: flex; align-items: center; justify-content: center;
  transition: all var(--dur-fast) var(--ease-out);
}
.back-btn:hover { background: var(--glass-bg-hover); }
.back-btn:active { transform: scale(0.96); }
.back-btn i { font-size: 20px; }
.count {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  background: var(--glass-bg);
  padding: 2px 10px;
  border-radius: var(--radius-full);
  border: 1px solid var(--glass-border);
}

/* 骨架屏 */
.skeleton-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}
.skeleton-card {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.skeleton-inner { display: flex; min-height: 100px; }
.skeleton-thumb {
  width: 100px; flex-shrink: 0;
  background: linear-gradient(90deg, var(--color-bg-elevated) 25%, var(--glass-bg) 50%, var(--color-bg-elevated) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.8s linear infinite;
}
.skeleton-body { flex: 1; padding: 16px; }
.skeleton-line {
  height: 12px; border-radius: 4px; margin-bottom: 8px;
  background: linear-gradient(90deg, var(--color-bg-elevated) 25%, var(--glass-bg) 50%, var(--color-bg-elevated) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.8s linear infinite;
}
.skeleton-line:nth-child(2) { width: 60%; }

/* 空状态 */
.empty {
  text-align: center;
  padding: var(--space-6);
  color: var(--color-text-tertiary);
}
.empty-icon {
  font-size: 48px;
  opacity: 0.2;
  margin-bottom: var(--space-4);
}
.empty .btn { margin-top: var(--space-4); }
.btn {
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-weight: 500;
  cursor: pointer;
}
.btn-primary {
  background: linear-gradient(135deg, var(--color-sakura), var(--color-violet));
  color: white;
}

/* 卡片网格 */
.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}

.project-card {
  position: relative;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  transition: all var(--dur-base) var(--ease-spring);
  backdrop-filter: blur(12px);
  animation: cardIn 300ms var(--ease-spring) both;
}
.project-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, transparent 30%, rgba(255,255,255,0.06) 50%, transparent 70%);
  transform: translateX(-100%);
  transition: transform 600ms var(--ease-out);
  pointer-events: none;
  z-index: 1;
}
.project-card:hover {
  transform: translateY(-4px);
  border-color: rgba(255, 143, 177, 0.3);
  box-shadow: 0 8px 24px rgba(255, 143, 177, 0.15);
}
.project-card:hover::before {
  transform: translateX(100%);
}

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
  background: linear-gradient(160deg, var(--color-bg-surface), var(--color-bg-elevated));
  display: flex;
  align-items: center;
  justify-content: center;
}
.thumb-icon {
  font-size: 36px;
  opacity: 0.35;
  color: var(--color-text-secondary);
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
  font-family: var(--font-display);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  color: var(--color-moon);
  font-weight: 500;
}

.badge {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.badge i { font-size: 12px; }
.exploration-conservative { background: rgba(99,102,241,.2); color: #a5b4fc; border: 1px solid rgba(99,102,241,.4); }
.exploration-standard { background: rgba(139,92,246,.2); color: #c4b5fd; border: 1px solid rgba(139,92,246,.4); }
.exploration-wild { background: rgba(236,72,153,.2); color: #f9a8d4; border: 1px solid rgba(236,72,153,.4); }
.status-not_started { background: rgba(156,163,175,.2); color: #d1d5db; border: 1px solid rgba(156,163,175,.4); }
.status-in_progress { background: rgba(251,191,36,.2); color: #fde68a; border: 1px solid rgba(251,191,36,.4); }
.status-completed { background: rgba(34,197,94,.2); color: #86efac; border: 1px solid rgba(34,197,94,.4); }

/* 操作按钮 */
.card-actions {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4) var(--space-3);
}
.btn-view {
  padding: 6px 12px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all var(--dur-fast) var(--ease-out);
}
.btn-view:hover { border-color: var(--color-violet); color: var(--color-violet); }
.btn-view:active { transform: scale(0.96); }
.btn-view i { font-size: 14px; }
.btn-read {
  padding: 6px 12px;
  background: linear-gradient(135deg, var(--color-sakura), var(--color-violet));
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all var(--dur-fast) var(--ease-out);
  box-shadow: 0 2px 8px rgba(255, 143, 177, 0.2);
}
.btn-read:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(255, 143, 177, 0.3); }
.btn-read:active:not(:disabled) { transform: scale(0.96); }
.btn-read:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-read i { font-size: 14px; }

/* "..." 菜单 */
.card-menu {
  position: absolute;
  top: 8px; right: 8px;
  width: 32px; height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  cursor: pointer;
  z-index: 2;
  opacity: 0;
  transition: opacity var(--dur-fast);
  background: rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(4px);
}
.project-card:hover .card-menu { opacity: 1; }
.card-menu i { font-size: 18px; color: var(--color-text-secondary); }

.card-menu-dropdown {
  position: absolute;
  top: 42px; right: 8px;
  z-index: 10;
  background: rgba(18, 10, 38, 0.95);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
  min-width: 120px;
  overflow: hidden;
  animation: menuIn 200ms var(--ease-spring);
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: var(--space-2) var(--space-4);
  background: none;
  border: none;
  text-align: left;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  cursor: pointer;
  transition: background var(--dur-fast);
}
.menu-item:hover:not(:disabled) { background: var(--glass-bg-hover); }
.menu-item:disabled { opacity: 0.5; cursor: not-allowed; }
.menu-danger { color: var(--color-error); }
.menu-danger:hover:not(:disabled) { background: rgba(248, 113, 113, 0.1); }

@media (prefers-reduced-motion: reduce) {
  .project-card { animation: none; opacity: 1; }
  .project-card::before { display: none; }
  .list-header { animation: none; }
  .skeleton-thumb, .skeleton-line { animation: none; }
}
@media (max-width: 375px) {
  .project-grid { grid-template-columns: 1fr; }
  .list-header h1 { font-size: var(--text-lg); }
}
</style>
