<script setup lang="ts">
/**
 * World 世界管理（琉璃宫升级版 v2）
 */
import { onMounted, computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import { useChaptersStore } from '@/stores/chapters'
import { rollbackProject } from '@/api/actions'

const route = useRoute()
const router = useRouter()
const projectsStore = useProjectsStore()
const chaptersStore = useChaptersStore()

const projectId = computed(() => route.params.projectId as string || 'demo-urban-romance')
const rollbackTo = ref(1)
const deleting = ref(false)
const rollingBack = ref(false)

async function load() {
  await projectsStore.loadOne(projectId.value)
  await chaptersStore.loadList(projectId.value)
}

async function doRollback() {
  if (!confirm(`确认回档到第 ${rollbackTo.value} 章？后续章节将永久删除。`)) return
  rollingBack.value = true
  try {
    await rollbackProject(projectId.value, rollbackTo.value)
    await load()
  } catch (e: any) {
    alert(`回档失败: ${e.message}`)
  } finally {
    rollingBack.value = false
  }
}

async function doDelete() {
  if (!confirm(`确认删除项目「${projectsStore.current?.name}」？此操作不可撤销。`)) return
  deleting.value = true
  try {
    await projectsStore.remove(projectId.value)
    router.push('/')
  } catch (e: any) {
    alert(`删除失败: ${e.message}`)
  } finally {
    deleting.value = false
  }
}

function enterChapter(n: number) {
  router.push({ name: 'reader', params: { projectId: projectId.value, chapterNum: n } })
}

onMounted(load)

const explorationLabels: Record<string, string> = {
  conservative: '保守',
  standard: '标准',
  wild: '狂野',
}
const explorationIcons: Record<string, string> = {
  conservative: 'shield',
  standard: 'scales',
  wild: 'planet',
}
</script>

<template>
  <div class="world">
    <!-- 封面 banner + 标题叠加 -->
    <div
      v-if="projectsStore.current"
      class="cover-banner"
      :class="projectsStore.current.cover_image_url ? 'has-image' : 'placeholder'"
      :style="projectsStore.current.cover_image_url
        ? { backgroundImage: `url(${projectsStore.current.cover_image_url})` }
        : {}"
    >
      <div class="cover-overlay"></div>
      <i v-if="!projectsStore.current.cover_image_url" class="ph ph-book-open cover-icon"></i>
      <div class="cover-title-area" v-if="projectsStore.current">
        <h1 class="cover-title">{{ projectsStore.current.name }}</h1>
        <div class="cover-badges">
          <span class="badge palette-badge">{{ projectsStore.current.palette }}</span>
          <span class="badge exploration-badge" v-if="projectsStore.current.exploration_level">
            <i :class="`ph ph-${explorationIcons[projectsStore.current.exploration_level] || 'scales'}`"></i>
            {{ explorationLabels[projectsStore.current.exploration_level] || '标准' }}
          </span>
          <span class="badge chapter-badge">
            <i class="ph ph-books"></i>
            {{ chaptersStore.count }} 章
          </span>
        </div>
      </div>
    </div>

    <div class="world-body">
      <!-- 左：信息面板 -->
      <section class="info-panel">
        <div class="panel-title"><i class="ph ph-info"></i>项目信息</div>
        <dl>
          <dt>章节数</dt>
          <dd>{{ chaptersStore.count }}</dd>
          <dt>调色板</dt>
          <dd>{{ projectsStore.current?.palette || '-' }}</dd>
          <dt>探索度</dt>
          <dd>{{ explorationLabels[projectsStore.current?.exploration_level || 'standard'] }}</dd>
          <dt>状态</dt>
          <dd>{{ projectsStore.projects.find(p => p.id === projectId)?.status === 'completed' ? '已完成' : projectsStore.projects.find(p => p.id === projectId)?.status === 'in_progress' ? '进行中' : '未启动' }}</dd>
        </dl>
        <button
          v-if="chaptersStore.count > 0"
          class="btn btn-primary"
          @click="enterChapter(chaptersStore.count)"
        >
          <i class="ph ph-book-open"></i>
          进入阅读
        </button>
        <p v-else class="hint-text">还未生成章节<br>请回首页对话中说「生成第 1 章」</p>
      </section>

      <!-- 中：章节列表 -->
      <section class="chapters-panel">
        <div class="panel-title">
          <i class="ph ph-books"></i>章节列表
          <span class="panel-count">{{ chaptersStore.count }}</span>
        </div>
        <div class="chapter-list">
          <div
            v-for="ch in chaptersStore.list"
            :key="ch.num"
            class="chapter-row"
            @click="enterChapter(ch.num)"
          >
            <span class="ch-num">#{{ ch.num }}</span>
            <div class="ch-info">
              <div class="ch-title">{{ ch.title }}</div>
              <div v-if="ch.summary" class="ch-summary">{{ ch.summary }}</div>
            </div>
            <i class="ph ph-arrow-right ch-arrow"></i>
          </div>
        </div>
      </section>

      <!-- 右：危险操作 -->
      <section class="ops-panel">
        <div class="panel-title"><i class="ph ph-warning"></i>危险操作</div>
        <div class="rollback-area">
          <label class="rollback-label">回档到章节</label>
          <div class="rollback-row">
            <input
              type="number"
              v-model.number="rollbackTo"
              :min="1"
              :max="chaptersStore.count"
              class="rollback-input"
            />
            <button
              class="btn btn-rollback"
              :disabled="rollingBack"
              @click="doRollback"
            >
              <i class="ph ph-arrow-counter-clockwise"></i>
              {{ rollingBack ? '回档中...' : '回档' }}
            </button>
          </div>
          <p class="rollback-hint">后续章节将永久删除</p>
        </div>
        <div class="divider"></div>
        <button
          class="btn btn-delete"
          :disabled="deleting"
          @click="doDelete"
        >
          <i class="ph ph-trash"></i>
          {{ deleting ? '删除中...' : '删除项目' }}
        </button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.world {
  padding: var(--space-5);
  max-width: 1200px;
  margin: 0 auto;
}

/* ===== 封面 banner + 标题叠加 ===== */
.cover-banner {
  width: 100%;
  height: 240px;
  border-radius: var(--radius-lg);
  position: relative;
  overflow: hidden;
  margin-bottom: var(--space-5);
  display: flex;
  align-items: flex-end;
  animation: bannerIn 600ms var(--ease-spring);
}
@keyframes bannerIn {
  from { transform: scale(1.05); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}
.cover-banner.has-image {
  background-size: cover;
  background-position: center top;
}
.cover-banner.placeholder {
  background: linear-gradient(135deg, var(--color-bg-surface) 0%, var(--color-bg-elevated) 100%);
  justify-content: center;
  align-items: center;
}
.cover-icon {
  font-size: 72px;
  opacity: 0.15;
  color: var(--color-text-secondary);
}
.cover-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom,
    rgba(10, 5, 20, 0.2) 0%,
    rgba(10, 5, 20, 0.5) 60%,
    rgba(10, 5, 20, 0.85) 100%);
}
.cover-title-area {
  position: relative;
  z-index: 1;
  padding: var(--space-5);
}
.cover-title {
  font-family: var(--font-display);
  font-size: var(--text-3xl);
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0 0 var(--space-2) 0;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
}
.cover-badges {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.badge {
  font-size: var(--text-xs);
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  backdrop-filter: blur(4px);
}
.badge i { font-size: 12px; }
.palette-badge {
  background: rgba(139, 92, 246, 0.3);
  color: #c4b5fd;
}
.exploration-badge {
  background: rgba(255, 143, 177, 0.25);
  color: var(--color-sakura-light);
}
.chapter-badge {
  background: rgba(255, 200, 87, 0.2);
  color: var(--color-moon);
}

/* ===== 3 栏布局 ===== */
.world-body {
  display: grid;
  grid-template-columns: 240px 1fr 240px;
  gap: var(--space-4);
}
@media (max-width: 1024px) {
  .world-body { grid-template-columns: 1fr; }
}

/* 面板通用 */
.info-panel,
.chapters-panel,
.ops-panel {
  background: var(--glass-bg);
  padding: var(--space-5);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(12px);
}
.info-panel { animation: fadeInLeft 400ms var(--ease-spring) 100ms both; }
.chapters-panel { animation: fadeInUp 400ms var(--ease-spring) 200ms both; }
.ops-panel {
  animation: fadeInRight 400ms var(--ease-spring) 300ms both;
  align-self: start;
  position: sticky;
  top: 80px;
  border-color: rgba(251, 191, 36, 0.25);
}
@keyframes fadeInLeft {
  from { opacity: 0; transform: translateX(-16px); }
  to { opacity: 1; transform: translateX(0); }
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes fadeInRight {
  from { opacity: 0; transform: translateX(16px); }
  to { opacity: 1; transform: translateX(0); }
}

.panel-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-sakura);
  margin-bottom: var(--space-4);
  display: flex;
  align-items: center;
  gap: 6px;
}
.panel-title i { font-size: 18px; }
.ops-panel .panel-title { color: var(--color-warning); }
.panel-count {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  background: var(--glass-bg);
  padding: 1px 8px;
  border-radius: var(--radius-full);
  margin-left: auto;
}

/* 信息面板 */
dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-2) var(--space-3);
  margin-bottom: var(--space-4);
}
dt {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}
dd {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

/* 按钮 */
.btn {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  transition: all var(--dur-fast) var(--ease-spring);
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: center;
  cursor: pointer;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-primary {
  background: linear-gradient(135deg, var(--color-sakura), var(--color-violet));
  color: white;
  width: 100%;
  box-shadow: var(--glow-sakura);
}
.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 0 36px rgba(255, 143, 177, 0.4), var(--glow-sakura);
}
.btn-primary:active:not(:disabled) {
  transform: scale(0.96);
}
.btn-rollback {
  background: transparent;
  border: 1px solid var(--color-warning);
  color: var(--color-warning);
  white-space: nowrap;
}
.btn-rollback:hover:not(:disabled) {
  background: rgba(251, 191, 36, 0.1);
}
.btn-delete {
  background: transparent;
  border: 1px solid var(--color-error);
  color: var(--color-error);
  width: 100%;
}
.btn-delete:hover:not(:disabled) {
  background: rgba(248, 113, 113, 0.1);
}

.hint-text {
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
  text-align: center;
  padding: var(--space-4) 0;
  line-height: 1.6;
}

/* 章节列表 */
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
  background: var(--color-bg-elevated);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  transition: all var(--dur-base) var(--ease-out);
  position: relative;
  overflow: hidden;
  cursor: pointer;
}
.chapter-row::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.04), transparent);
  transform: translateX(-100%);
  transition: transform 600ms var(--ease-out);
  pointer-events: none;
}
.chapter-row:hover {
  background: var(--glass-bg-hover);
  border-color: rgba(255, 143, 177, 0.3);
}
.chapter-row:hover::before {
  transform: translateX(100%);
}
.ch-num {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--color-moon);
  flex-shrink: 0;
  min-width: 36px;
}
.ch-info {
  flex: 1;
  min-width: 0;
}
.ch-title {
  font-size: var(--text-sm);
  font-weight: 500;
  margin-bottom: 2px;
  color: var(--color-text-primary);
}
.ch-summary {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ch-arrow {
  font-size: 16px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;
  transition: transform var(--dur-fast) var(--ease-out), color var(--dur-fast);
}
.chapter-row:hover .ch-arrow {
  color: var(--color-sakura);
  transform: translateX(4px);
}

/* 危险操作 */
.rollback-area {
  margin-bottom: var(--space-3);
}
.rollback-label {
  display: block;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
}
.rollback-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.rollback-input {
  width: 72px;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-elevated);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-spring), box-shadow var(--dur-fast) var(--ease-spring);
}
.rollback-input:focus {
  border-color: var(--color-warning);
  box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.15);
}
.rollback-hint {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  margin: var(--space-2) 0 0;
}

.divider {
  height: 1px;
  background: var(--glass-border);
  margin: var(--space-4) 0;
}

@media (prefers-reduced-motion: reduce) {
  .cover-banner,
  .info-panel,
  .chapters-panel,
  .ops-panel {
    animation: none;
    opacity: 1;
  }
  .chapter-row::before { display: none; }
}
@media (max-width: 375px) {
  .cover-banner { height: 160px; }
  .cover-title { font-size: var(--text-2xl); }
}
</style>
