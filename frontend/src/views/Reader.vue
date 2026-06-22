<script setup lang="ts">
/**
 * Reader 章节阅读（v0.5 新增 summary 展示）
 *
 * 3 栏 Bento：左项目信息 / 中章节正文 / 右干预面板
 */
import { ref, onMounted, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChaptersStore } from '@/stores/chapters'
import { useProjectsStore } from '@/stores/projects'

const route = useRoute()
const router = useRouter()
const chaptersStore = useChaptersStore()
const projectsStore = useProjectsStore()

const projectId = computed(() => route.params.projectId as string)
const chapterNum = computed(() => parseInt(route.params.chapterNum as string) || 1)

const intervention = ref('')
const showDrawer = ref(false)

async function loadAll() {
  await projectsStore.loadOne(projectId.value)
  await chaptersStore.loadList(projectId.value)
  await chaptersStore.loadOne(projectId.value, chapterNum.value)
}

function goToChapter(n: number) {
  router.push({ name: 'reader', params: { projectId: projectId.value, chapterNum: n } })
}

/** v0.8: 切换项目探索度 */
async function onExplorationChange(newLevel: string) {
  if (!['conservative', 'standard', 'wild'].includes(newLevel)) return
  try {
    await projectsStore.updateExplorationLevel(projectId.value, newLevel as any)
    console.log(`[Reader] 探索度已切换为 ${newLevel}`)
  } catch (e: any) {
    console.error('[Reader] 切换探索度失败', e)
    alert(`切换失败: ${e.message}`)
  }
}

async function nextChapter() {
  const n = chapterNum.value + 1
  try {
    await chaptersStore.generate(projectId.value, {
      intervention: intervention.value || undefined
    })
    intervention.value = ''
    await goToChapter(n)
  } catch (e) {
    // 错误已存 store.error
  }
}

async function submitIntervention() {
  if (!intervention.value.trim()) return
  // v0.5: 干预保存到当前章节 metadata，下次 generate 应用
  alert(`已记录干预：${intervention.value}\n下次"下一章"生成时应用`)
}

onMounted(loadAll)
watch(() => route.params, loadAll)
</script>

<template>
  <div class="reader">
    <!-- Header -->
    <header class="reader-header">
      <button class="back-btn" @click="router.push({ name: 'world', params: { projectId } })">←</button>
      <div class="project-info" v-if="projectsStore.current">
        <h1 class="project-name">{{ projectsStore.current.name }}</h1>
        <span class="palette">{{ projectsStore.current.palette }}</span>
        <!-- v0.8: 探索度下拉 (conservative/standard/wild) -->
        <div class="exploration-control" v-if="projectsStore.current">
          <label class="exploration-label">探索度</label>
          <select
            class="exploration-select"
            :value="projectsStore.current.exploration_level"
            @change="onExplorationChange(($event.target as HTMLSelectElement).value)"
          >
            <option value="conservative">🛡️ 保守</option>
            <option value="standard">⚖️ 标准</option>
            <option value="wild">🌌 狂野</option>
          </select>
        </div>
      </div>
      <button class="drawer-toggle" @click="showDrawer = !showDrawer">📚 章节列表</button>
    </header>

    <div class="reader-body">
      <!-- 左：章节导航 -->
      <aside class="left-pane">
        <div class="chapter-nav">
          <button :disabled="chapterNum <= 1" @click="goToChapter(chapterNum - 1)">← 上一章</button>
          <button @click="goToChapter(chapterNum + 1)" v-if="chapterNum < chaptersStore.count">下一章 →</button>
        </div>
        <div class="progress">
          <div class="progress-bar" :style="{ width: `${(chapterNum / Math.max(chaptersStore.count, 1)) * 100}%` }"></div>
          <span class="progress-text">{{ chapterNum }} / {{ chaptersStore.count }}</span>
        </div>
      </aside>

      <!-- 中：章节正文 -->
      <main class="center-pane">
        <div v-if="chaptersStore.loading" class="loading">加载中...</div>
        <div v-else-if="chaptersStore.current" class="chapter-content">
          <!-- v0.5 关键：summary 展示 -->
          <div v-if="chaptersStore.currentSummary" class="summary-capsule fade-in">
            <span class="summary-label">本章概要</span>
            <span class="summary-text">{{ chaptersStore.currentSummary }}</span>
          </div>
          <h1 class="chapter-title">{{ chaptersStore.current.title }}</h1>
          <div class="chapter-meta">
            <span>{{ chaptersStore.current.word_count }} 字</span>
            <span v-if="chaptersStore.current.generated_at">·</span>
            <span v-if="chaptersStore.current.generated_at">{{ new Date(chaptersStore.current.generated_at).toLocaleDateString() }}</span>
          </div>
          <article class="prose">
            <pre>{{ chaptersStore.current.content }}</pre>
          </article>

          <!-- 章尾：下一章按钮 -->
          <div class="chapter-footer">
            <button
              v-if="!chaptersStore.generating"
              class="btn btn-primary next-btn"
              @click="nextChapter"
            >
              ✨ 生成下一章
            </button>
            <div v-else class="generating">
              <div class="spinner"></div>
              <span>正在生成下一章（30-60s）...</span>
            </div>
          </div>
        </div>
      </main>

      <!-- 右：干预面板 -->
      <aside class="right-pane">
        <h3 class="pane-title">🎭 干预</h3>
        <textarea
          v-model="intervention"
          placeholder="下一章的剧情要求...（留空则自由生成）"
          class="intervention-textarea"
          rows="6"
        ></textarea>
        <button class="btn btn-secondary" @click="submitIntervention" :disabled="!intervention.trim()">
          记录干预
        </button>
        <p class="hint">干预会在下一章生成时应用</p>
      </aside>
    </div>

    <!-- 章节列表 drawer -->
    <transition name="slide">
      <div v-if="showDrawer" class="drawer">
        <div class="drawer-header">
          <h3>章节列表</h3>
          <button @click="showDrawer = false">×</button>
        </div>
        <div class="drawer-list">
          <div
            v-for="ch in chaptersStore.list"
            :key="ch.num"
            class="drawer-item"
            :class="{ active: ch.num === chapterNum }"
            @click="goToChapter(ch.num); showDrawer = false"
          >
            <div class="drawer-num">#{{ ch.num }}</div>
            <div class="drawer-info">
              <div class="drawer-title">{{ ch.title }}</div>
              <div v-if="ch.summary" class="drawer-summary">{{ ch.summary }}</div>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.reader {
  padding: var(--space-4) 0;
}

.reader-header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
  padding: var(--space-3) var(--space-4);
  background: var(--color-night-2);
  border-radius: var(--radius-md);
}

.back-btn {
  font-size: var(--text-2xl);
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  background: var(--color-night-3);
  transition: all var(--motion-fast) var(--ease-out);
}
.back-btn:hover { background: var(--color-accent-3); }

.project-info {
  flex: 1;
}
.project-name {
  font-size: var(--text-lg);
  margin-bottom: var(--space-1);
}
.palette {
  font-size: var(--text-xs);
  color: var(--color-text-dim);
  background: rgba(139, 92, 246, 0.2);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

/* v0.8: 探索度控制 */
.exploration-control {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: var(--space-3);
}
.exploration-label {
  font-size: var(--text-xs);
  color: var(--color-text-dim);
}
.exploration-select {
  padding: 2px 8px;
  font-size: var(--text-xs);
  background: var(--color-night-3);
  color: var(--color-text);
  border: 1px solid var(--color-night-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.exploration-select:hover {
  border-color: var(--color-accent, #8b5cf6);
}

.drawer-toggle {
  padding: var(--space-2) var(--space-4);
  background: var(--color-night-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}
.drawer-toggle:hover { background: var(--color-accent-3); }

.reader-body {
  display: grid;
  grid-template-columns: 200px 1fr 280px;
  gap: var(--space-4);
}

@media (max-width: 1024px) {
  .reader-body { grid-template-columns: 1fr; }
}

/* Left */
.left-pane {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.chapter-nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.chapter-nav button {
  padding: var(--space-2) var(--space-3);
  background: var(--color-night-2);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  text-align: left;
  transition: all var(--motion-fast) var(--ease-out);
}
.chapter-nav button:hover:not(:disabled) {
  background: var(--color-accent-3);
  color: white;
}
.chapter-nav button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.progress {
  position: relative;
  height: 8px;
  background: var(--color-night-3);
  border-radius: var(--radius-full);
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--color-accent-1), var(--color-accent-2));
  transition: width 0.3s;
}
.progress-text {
  display: block;
  text-align: center;
  font-size: var(--text-xs);
  color: var(--color-text-dim);
  margin-top: var(--space-2);
}

/* Center */
.center-pane {
  min-height: 70vh;
}

.loading {
  text-align: center;
  padding: var(--space-7);
  color: var(--color-text-dim);
}

/* v0.5 关键：summary 胶囊 */
.summary-capsule {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: linear-gradient(135deg, rgba(255, 143, 177, 0.15), rgba(139, 92, 246, 0.1));
  border: 1px solid var(--color-accent-1);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-5);
  font-size: var(--text-sm);
}
.summary-label {
  color: var(--color-accent-1);
  font-weight: 600;
  white-space: nowrap;
}
.summary-text {
  color: var(--color-text);
  flex: 1;
}

.chapter-title {
  font-size: var(--text-3xl);
  margin-bottom: var(--space-3);
  color: var(--color-accent-1);
}

.chapter-meta {
  display: flex;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-dim);
  margin-bottom: var(--space-5);
}

.prose pre {
  font-family: var(--font-body);
  font-size: var(--text-base);
  line-height: 1.8;
  color: var(--color-text);
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
}

.chapter-footer {
  margin-top: var(--space-7);
  text-align: center;
  padding: var(--space-6);
  background: var(--color-night-2);
  border-radius: var(--radius-md);
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
.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-secondary {
  background: transparent;
  border: 1px solid var(--color-accent-3);
  color: var(--color-accent-3);
}
.btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }

.next-btn {
  font-size: var(--text-lg);
  padding: var(--space-4) var(--space-7);
}

.generating {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  color: var(--color-accent-2);
}
.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--color-night-3);
  border-top-color: var(--color-accent-1);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* Right */
.right-pane {
  background: var(--color-night-2);
  padding: var(--space-5);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  align-self: start;
  position: sticky;
  top: 80px;
}

.pane-title {
  font-size: var(--text-lg);
  color: var(--color-accent-1);
}

.intervention-textarea {
  resize: vertical;
  min-height: 120px;
  font-size: var(--text-sm);
}

.hint {
  font-size: var(--text-xs);
  color: var(--color-text-faint);
  margin: 0;
}

/* Drawer */
.drawer {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 360px;
  background: var(--color-night-1);
  border-left: 1px solid var(--color-night-3);
  z-index: 200;
  display: flex;
  flex-direction: column;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4);
  border-bottom: 1px solid var(--color-night-3);
}
.drawer-header button {
  font-size: var(--text-2xl);
  width: 32px;
  height: 32px;
}

.drawer-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-3);
}

.drawer-item {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out);
}
.drawer-item:hover,
.drawer-item.active {
  background: var(--color-night-2);
}
.drawer-num {
  font-family: var(--font-mono);
  color: var(--color-accent-2);
  flex-shrink: 0;
}
.drawer-title {
  font-size: var(--text-sm);
  margin-bottom: 2px;
}
.drawer-summary {
  font-size: var(--text-xs);
  color: var(--color-text-dim);
  line-height: 1.4;
}

.slide-enter-active, .slide-leave-active {
  transition: transform 0.25s;
}
.slide-enter-from, .slide-leave-to {
  transform: translateX(100%);
}
</style>
