<script setup lang="ts">
/**
 * World 世界管理（v0.5 接入后端）
 *
 * 项目信息 + 章节列表 + 操作（回档/删除/进入阅读）
 */
import { onMounted, computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import { useChaptersStore } from '@/stores/chapters'
import { rollbackProject, onboardingStep } from '@/api/actions'

const route = useRoute()
const router = useRouter()
const projectsStore = useProjectsStore()
const chaptersStore = useChaptersStore()

const projectId = computed(() => route.params.projectId as string || 'demo-urban-romance')
const rollbackTo = ref(1)

async function load() {
  await projectsStore.loadOne(projectId.value)
  await chaptersStore.loadList(projectId.value)
}

async function doRollback() {
  if (!confirm(`⚠️ 确认回档到第 ${rollbackTo.value} 章？后续章节将永久删除。`)) return
  await rollbackProject(projectId.value, rollbackTo.value)
  await load()
}

async function doDelete() {
  if (!confirm(`⚠️ 确认删除项目 ${projectId.value}？此操作不可撤销。`)) return
  await projectsStore.remove(projectId.value)
  router.push('/')
}

/** v0.8.3: 生成第 1 章 (onboard 完成后) */
const generating = ref(false)
const genError = ref<string | null>(null)
async function generateFirstChapter() {
  if (generating.value) return
  if (!confirm('🚀 开始生成第 1 章？预计耗时 30-60 秒。')) return
  generating.value = true
  genError.value = null
  try {
    await onboardingStep(projectId.value, '5', {})
    await chaptersStore.loadList(projectId.value)
    if (chaptersStore.count > 0) {
      enterChapter(1)
    }
  } catch (e: any) {
    genError.value = e.message || '生成失败'
  } finally {
    generating.value = false
  }
}

function enterChapter(n: number) {
  router.push({ name: 'reader', params: { projectId: projectId.value, chapterNum: n } })
}

onMounted(load)
</script>

<template>
  <div class="world">
    <!-- v0.9: 世界封面图 banner（始终展示，无图用占位） -->
    <div
      v-if="projectsStore.current"
      class="world-cover-banner"
      :class="projectsStore.current.cover_image_url ? 'world-cover-has-image' : 'world-cover-placeholder'"
      :style="projectsStore.current.cover_image_url
        ? { backgroundImage: `url(${projectsStore.current.cover_image_url})` }
        : {}"
    >
      <div class="world-cover-overlay"></div>
      <span v-if="!projectsStore.current.cover_image_url" class="world-cover-placeholder-icon">📖</span>
    </div>

    <header class="world-header" v-if="projectsStore.current">
      <h1>{{ projectsStore.current.name }}</h1>
      <span class="palette">{{ projectsStore.current.palette }}</span>
    </header>

    <div class="world-body">
      <section class="info-panel">
        <h3>项目信息</h3>
        <dl>
          <dt>章节数</dt>
          <dd>{{ chaptersStore.count }}</dd>
          <dt>调色板</dt>
          <dd>{{ projectsStore.current?.palette || '-' }}</dd>
        </dl>
        <!-- v0.8.3: 无章节时显示生成第 1 章入口 (onboard 完成但未生成) -->
        <button v-if="chaptersStore.count === 0" class="btn btn-primary" :disabled="generating" @click="generateFirstChapter">
          {{ generating ? '生成中...' : '✨ 生成第 1 章' }}
        </button>
        <button v-else class="btn btn-primary" @click="enterChapter(chaptersStore.count || 1)">
          📖 进入阅读
        </button>
        <p v-if="genError" class="error-text">{{ genError }}</p>
      </section>

      <section class="chapters-panel">
        <h3>章节列表</h3>
        <div class="chapter-list">
          <div
            v-for="ch in chaptersStore.list"
            :key="ch.num"
            class="chapter-row"
          >
            <span class="ch-num">#{{ ch.num }}</span>
            <div class="ch-info">
              <div class="ch-title">{{ ch.title }}</div>
              <div v-if="ch.summary" class="ch-summary">{{ ch.summary }}</div>
            </div>
            <button class="btn-mini" @click="enterChapter(ch.num)">阅读</button>
          </div>
        </div>
      </section>

      <section class="ops-panel">
        <h3>⚠️ 危险操作</h3>
        <div class="rollback">
          <label class="rollback-label">回档到章节</label>
          <div class="rollback-row">
            <input type="number" v-model.number="rollbackTo" :min="1" :max="chaptersStore.count" />
            <button class="btn btn-danger" @click="doRollback">回档</button>
          </div>
        </div>
        <button class="btn btn-danger" @click="doDelete">删除项目</button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.world {
  padding: var(--space-4) 0;
}

/* v0.9: 封面图 banner */
.world-cover-banner {
  width: 100%;
  height: 240px;
  border-radius: var(--radius-lg);
  position: relative;
  overflow: hidden;
  margin-bottom: var(--space-5);
}
.world-cover-has-image {
  background-size: cover;
  background-position: center top;
}
.world-cover-placeholder {
  background: linear-gradient(135deg, var(--color-night-2) 0%, var(--color-night-3) 100%);
  display: flex;
  align-items: center;
  justify-content: center;
}
.world-cover-placeholder-icon {
  font-size: 72px;
  opacity: 0.15;
}
.world-cover-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    rgba(10, 5, 20, 0) 0%,
    rgba(10, 5, 20, 0.7) 100%
  );
}

.world-header {
  margin-bottom: var(--space-5);
}
.world-header h1 {
  font-size: var(--text-3xl);
  color: var(--color-accent-1);
  display: inline-block;
  margin-right: var(--space-3);
}
.palette {
  font-size: var(--text-sm);
  color: var(--color-text-dim);
  background: rgba(139, 92, 246, 0.2);
  padding: 4px 12px;
  border-radius: var(--radius-md);
}

.world-body {
  display: grid;
  grid-template-columns: 240px 1fr 240px;
  gap: var(--space-4);
}

@media (max-width: 1024px) {
  .world-body { grid-template-columns: 1fr; }
}

.info-panel,
.chapters-panel,
.ops-panel {
  background: var(--color-night-2);
  padding: var(--space-5);
  border-radius: var(--radius-md);
}

.info-panel h3,
.chapters-panel h3,
.ops-panel h3 {
  font-size: var(--text-base);
  color: var(--color-accent-1);
  margin-bottom: var(--space-4);
}

dl {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}
dt {
  color: var(--color-text-dim);
  font-size: var(--text-sm);
}
dd {
  margin: 0;
  font-size: var(--text-sm);
}

.chapter-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-height: 70vh;
  overflow-y: auto;
}

.chapter-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--color-night-3);
  border-radius: var(--radius-md);
  transition: background var(--motion-fast) var(--ease-out);
}
.chapter-row:hover {
  background: var(--color-night-2);
  border: 1px solid var(--color-accent-1);
}
.ch-num {
  font-family: var(--font-mono);
  color: var(--color-accent-2);
  flex-shrink: 0;
  min-width: 40px;
}
.ch-info { flex: 1; min-width: 0; }
.ch-title {
  font-size: var(--text-sm);
  margin-bottom: 2px;
}
.ch-summary {
  font-size: var(--text-xs);
  color: var(--color-text-dim);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.btn {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  transition: all var(--motion-fast) var(--ease-out);
}
.btn-primary {
  background: linear-gradient(135deg, var(--color-accent-1), var(--color-accent-3));
  color: white;
  width: 100%;
  margin-top: var(--space-3);
}
.btn-danger {
  background: transparent;
  border: 1px solid var(--color-error);
  color: var(--color-error);
}
.btn-danger:hover {
  background: rgba(248, 113, 113, 0.1);
}

.btn-mini {
  padding: var(--space-1) var(--space-3);
  background: var(--color-night-2);
  border: 1px solid var(--color-night-3);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--color-text-dim);
  flex-shrink: 0;
}
.btn-mini:hover {
  border-color: var(--color-accent-1);
  color: var(--color-accent-1);
}

.ops-panel {
  align-self: start;
  position: sticky;
  top: 80px;
}

.rollback {
  margin-bottom: var(--space-4);
}
.rollback-label {
  display: block;
  font-size: var(--text-sm);
  color: var(--color-text-dim);
  margin-bottom: var(--space-2);
}
.rollback-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.rollback-row input {
  width: 80px;
  padding: var(--space-2);
}
.ops-panel .btn {
  width: 100%;
  margin-bottom: var(--space-2);
}
</style>
