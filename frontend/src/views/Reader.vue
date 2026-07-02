<script setup lang="ts">
/**
 * Reader 章节阅读（琉璃宫升级版 v3）
 * - 左栏玻璃面板：封面 + 章节导航 + 进度 + 生成下一章
 * - 底部干预栏：单行输入 + 展开
 * - 章尾：完结标记 + 生成按钮
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
const interventionExpanded = ref(false)
const recordFeedback = ref(false)

async function loadAll() {
  await projectsStore.loadOne(projectId.value)
  await chaptersStore.loadList(projectId.value)
  await chaptersStore.loadOne(projectId.value, chapterNum.value)
}

function goToChapter(n: number) {
  router.push({ name: 'reader', params: { projectId: projectId.value, chapterNum: n } })
}

async function onExplorationChange(newLevel: string) {
  if (!['conservative', 'standard', 'wild'].includes(newLevel)) return
  try {
    await projectsStore.updateExplorationLevel(projectId.value, newLevel as any)
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
    interventionExpanded.value = false
    await goToChapter(n)
  } catch (e) { /* 错误已存 store.error */ }
}

async function submitIntervention() {
  if (!intervention.value.trim()) return
  recordFeedback.value = true
  setTimeout(() => { recordFeedback.value = false }, 2000)
}

onMounted(loadAll)
watch(() => route.params, loadAll)

const explorationLevels = [
  { value: 'conservative', label: '保守', icon: 'shield' },
  { value: 'standard', label: '标准', icon: 'scales' },
  { value: 'wild', label: '狂野', icon: 'planet' },
]

const currentExploration = computed(() => projectsStore.current?.exploration_level || 'standard')
</script>

<template>
  <div class="reader">
    <!-- Header（虚化封面图背景） -->
    <header
      class="reader-header"
      :class="{ 'has-cover': projectsStore.current?.cover_image_url }"
    >
      <div
        v-if="projectsStore.current?.cover_image_url"
        class="header-bg"
        :style="{ backgroundImage: `url(${projectsStore.current.cover_image_url})` }"
      ></div>
      <div class="header-overlay"></div>
      <div class="header-content">
        <button class="header-btn" @click="router.push({ name: 'world', params: { projectId } })">
          <i class="ph ph-arrow-left"></i>
        </button>
        <h1 class="reader-title" v-if="projectsStore.current">{{ projectsStore.current.name }}</h1>
        <!-- 探索度 toggle -->
        <div class="exploration-toggle" :data-level="currentExploration">
          <div class="toggle-slider" :data-level="currentExploration"></div>
          <button
            v-for="lvl in explorationLevels"
            :key="lvl.value"
            class="toggle-label"
            :class="{ active: currentExploration === lvl.value }"
            :data-level="lvl.value"
            @click="onExplorationChange(lvl.value)"
          >
            <i :class="`ph ph-${lvl.icon}`"></i>
            {{ lvl.label }}
          </button>
        </div>
        <button class="header-btn header-btn-wide" @click="showDrawer = !showDrawer">
          <i class="ph ph-books"></i>
          <span>章节</span>
        </button>
      </div>
    </header>

    <div class="reader-body">
      <!-- 左栏：玻璃面板 -->
      <aside class="left-col">
        <div
          class="cover-thumb"
          :class="projectsStore.current?.cover_image_url ? 'has-cover' : ''"
          :style="projectsStore.current?.cover_image_url
            ? { backgroundImage: `url(${projectsStore.current.cover_image_url})` }
            : {}"
        >
          <i v-if="!projectsStore.current?.cover_image_url" class="ph ph-book-open"></i>
        </div>

        <button class="nav-btn" :disabled="chapterNum <= 1" @click="goToChapter(chapterNum - 1)">
          <i class="ph ph-arrow-left"></i><span>上一章</span>
        </button>
        <button class="nav-btn" v-if="chapterNum < chaptersStore.count" @click="goToChapter(chapterNum + 1)">
          <i class="ph ph-arrow-right"></i><span>下一章</span>
        </button>

        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: `${(chapterNum / Math.max(chaptersStore.count, 1)) * 100}%` }"></div>
        </div>
        <div class="progress-text">
          第 {{ chapterNum }} / {{ chaptersStore.count }} 章
        </div>

        <!-- 生成下一章 -->
        <button
          v-if="!chaptersStore.generating"
          class="btn-generate"
          @click="nextChapter"
        >
          <i class="ph ph-sparkle"></i>
          <span>生成下一章</span>
        </button>
        <div v-else class="generating-state">
          <div class="spinner"></div>
          <span>生成中...</span>
        </div>
      </aside>

      <!-- 中栏：正文 -->
      <main class="center-col">
        <!-- 骨架屏 -->
        <div v-if="chaptersStore.loading" class="skeleton-wrap">
          <div class="skeleton-line title"></div>
          <div class="skeleton-line meta"></div>
          <div class="skeleton-line w-100"></div>
          <div class="skeleton-line w-90"></div>
          <div class="skeleton-line w-100"></div>
          <div class="skeleton-line w-80"></div>
          <div class="skeleton-line w-100"></div>
          <div class="skeleton-line w-70"></div>
        </div>

        <div v-else-if="chaptersStore.current" class="chapter-content">
          <!-- 概要胶囊 -->
          <div v-if="chaptersStore.currentSummary" class="summary-pill">
            <i class="ph ph-sparkle"></i>
            <div>
              <strong>本章概要：</strong>{{ chaptersStore.currentSummary }}
            </div>
          </div>

          <h1 class="chapter-title">{{ chaptersStore.current.title }}</h1>

          <div class="chapter-meta">
            <span><i class="ph ph-text-aa"></i> {{ chaptersStore.current.word_count }} 字</span>
            <span v-if="chaptersStore.current.generated_at">·</span>
            <span v-if="chaptersStore.current.generated_at"><i class="ph ph-clock"></i> {{ new Date(chaptersStore.current.generated_at).toLocaleDateString() }}</span>
          </div>

          <div class="prose">
            <pre>{{ chaptersStore.current.content }}</pre>
          </div>

          <!-- 章尾 -->
          <div class="chapter-tail">
            <div class="tail-label">— 第 {{ chapterNum }} 章 完 —</div>
          </div>
        </div>
      </main>
    </div>

    <!-- 底部干预栏 -->
    <div class="intervention-bar" :class="{ expanded: interventionExpanded }">
      <transition name="bar-swap" mode="out-in">
        <!-- 折叠态 -->
        <div v-if="!interventionExpanded" class="bar-collapsed" key="collapsed">
          <i class="ph ph-mask-theater bar-icon"></i>
          <input
            v-model="intervention"
            placeholder="下一章的剧情要求...（留空则自由生成）"
            class="bar-input"
            @keydown.enter.exact.prevent="submitIntervention"
          />
          <button class="bar-submit" @click="submitIntervention" :disabled="!intervention.trim()">
            提交
          </button>
          <button v-if="recordFeedback" class="bar-feedback">
            <i class="ph ph-check-circle"></i>
          </button>
          <button class="bar-expand" @click="interventionExpanded = true">
            <i class="ph ph-arrows-out-vertical"></i>
          </button>
        </div>

        <!-- 展开态 -->
        <div v-else class="bar-expanded" key="expanded">
          <div class="bar-expanded-header">
            <span class="bar-title"><i class="ph ph-mask-theater"></i> 作者干预</span>
            <button class="bar-collapse" @click="interventionExpanded = false">
              <i class="ph ph-arrows-in-vertical"></i>
            </button>
          </div>
          <div class="bar-expanded-body">
            <textarea
              v-model="intervention"
              placeholder="在此输入你想让 AI 知道的情节走向、伏笔或角色设定…"
              class="bar-textarea"
              rows="4"
            ></textarea>
            <div class="bar-expanded-actions">
              <button class="bar-submit" @click="submitIntervention" :disabled="!intervention.trim()">
                提交
              </button>
              <span v-if="recordFeedback" class="bar-feedback-text">
                <i class="ph ph-check-circle"></i> 已记录
              </span>
              <span class="bar-hint">干预会在下一章生成时应用</span>
            </div>
          </div>
        </div>
      </transition>
    </div>

    <!-- 章节列表 drawer -->
    <transition name="slide">
      <div v-if="showDrawer" class="drawer">
        <div class="drawer-header">
          <h2>章节列表</h2>
          <button class="drawer-close" @click="showDrawer = false">
            <i class="ph ph-x"></i>
          </button>
        </div>
        <div class="drawer-list">
          <div
            v-for="ch in chaptersStore.list"
            :key="ch.num"
            class="drawer-item"
            :class="{ active: ch.num === chapterNum }"
            @click="goToChapter(ch.num); showDrawer = false"
          >
            <span class="drawer-num">#{{ ch.num }}</span>
            <span class="drawer-title">{{ ch.title }}</span>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.reader {
  padding: var(--space-4);
  padding-bottom: 72px;
}

/* ===== Header ===== */
.reader-header {
  position: relative;
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
  overflow: hidden;
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  animation: fadeInDown 300ms var(--ease-spring);
}
.header-bg {
  position: absolute;
  inset: 0;
  background-size: cover;
  background-position: center;
  filter: blur(8px);
  transform: scale(1.1);
}
.header-overlay {
  position: absolute;
  inset: 0;
  background: rgba(10, 5, 20, 0.6);
}
.header-content {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.header-btn {
  width: 36px; height: 36px;
  border-radius: var(--radius-full);
  background: rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  transition: all var(--dur-fast) var(--ease-spring);
  flex-shrink: 0;
}
.header-btn:hover { background: var(--color-violet); }
.header-btn:active { transform: scale(0.96); }
.header-btn i { font-size: 18px; }
.header-btn-wide {
  width: auto;
  padding: 0 14px;
  gap: 6px;
  font-size: var(--text-sm);
}
.reader-title {
  font-family: var(--font-display);
  font-size: var(--text-lg);
  font-weight: 600;
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
  margin: 0;
}

/* 探索度 toggle（slider 指示器） */
.exploration-toggle {
  display: flex;
  align-items: center;
  background: rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(4px);
  padding: 3px;
  border-radius: var(--radius-full);
  position: relative;
  flex-shrink: 0;
  transition: background 300ms ease;
}
.exploration-toggle[data-level="conservative"] { background: rgba(99, 102, 241, 0.25); }
.exploration-toggle[data-level="standard"] { background: rgba(139, 92, 246, 0.25); }
.exploration-toggle[data-level="wild"] { background: rgba(236, 72, 153, 0.25); }
.toggle-slider {
  position: absolute;
  top: 3px; bottom: 3px;
  width: calc((100% - 6px) / 3);
  border-radius: var(--radius-full);
  z-index: 1;
  transition: transform 300ms var(--ease-spring), background 300ms ease;
}
.toggle-slider[data-level="conservative"] { transform: translateX(0); background: var(--color-indigo, #6366F1); }
.toggle-slider[data-level="standard"] { transform: translateX(100%); background: var(--color-violet); }
.toggle-slider[data-level="wild"] { transform: translateX(200%); background: var(--color-pink, #EC4899); }
.toggle-label {
  padding: 5px 12px;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  position: relative;
  z-index: 2;
  transition: color 300ms;
  cursor: pointer;
  border: none;
  background: none;
  display: flex;
  align-items: center;
  gap: 4px;
}
.toggle-label.active {
  color: #fff;
  font-weight: 600;
}
.toggle-label i { font-size: 12px; }

/* ===== 2 栏布局 ===== */
.reader-body {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: var(--space-4);
}
@media (max-width: 1024px) {
  .reader-body { grid-template-columns: 1fr; }
}

/* ===== 左栏（玻璃面板） ===== */
.left-col {
  background: var(--glass-bg);
  padding: var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(12px);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  animation: fadeInLeft 400ms var(--ease-spring) 100ms both;
  align-self: start;
  position: sticky;
  top: var(--space-4);
}
@keyframes fadeInLeft {
  from { opacity: 0; transform: translateX(-12px); }
  to { opacity: 1; transform: translateX(0); }
}

.cover-thumb {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: linear-gradient(135deg, var(--color-bg-surface), var(--color-bg-elevated));
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--glass-border);
}
.cover-thumb.has-cover {
  background-size: cover;
  background-position: center;
  border: none;
}
.cover-thumb i {
  font-size: 48px;
  opacity: 0.5;
  color: var(--color-text-secondary);
}

.nav-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  transition: all var(--dur-base) var(--ease-spring);
  justify-content: center;
}
.nav-btn i { font-size: 16px; }
.nav-btn:hover:not(:disabled) {
  background: var(--color-violet);
  color: #fff;
}
.nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.progress-bar {
  width: 100%;
  height: 6px;
  border-radius: var(--radius-full);
  background: var(--color-bg-elevated);
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-sakura), var(--color-moon));
  border-radius: var(--radius-full);
  transition: width 300ms var(--ease-spring);
}
.progress-text {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  text-align: center;
  font-family: var(--font-mono);
}

/* 生成下一章按钮 */
.btn-generate {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-sakura), var(--color-violet));
  color: #fff;
  font-size: var(--text-base);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  box-shadow: var(--glow-sakura);
  transition: transform var(--dur-base) var(--ease-spring), box-shadow var(--dur-base) var(--ease-spring);
}
.btn-generate i { font-size: 20px; }
.btn-generate:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 36px rgba(255, 143, 177, 0.5), var(--glow-sakura);
}
.btn-generate:active {
  transform: scale(0.96);
  transition: transform 100ms var(--ease-in);
}
.generating-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-3);
  color: var(--color-moon);
  font-size: var(--text-sm);
}
.spinner {
  width: 18px; height: 18px;
  border: 2px solid transparent;
  border-top-color: var(--color-sakura);
  border-right-color: var(--color-sakura);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ===== 中栏 ===== */
.center-col {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  animation: fadeInUp 400ms var(--ease-spring) 200ms both;
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 骨架屏 */
.skeleton-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 68ch;
  margin: 0 auto;
}
.skeleton-line {
  height: 14px;
  border-radius: var(--radius-sm);
  background: linear-gradient(90deg, var(--color-bg-elevated) 0%, var(--glass-bg) 50%, var(--color-bg-elevated) 100%);
  background-size: 200% 100%;
  animation: shimmer 1.8s linear infinite;
}
.skeleton-line.title { height: 28px; width: 60%; }
.skeleton-line.meta { height: 12px; width: 30%; }
.skeleton-line.w-100 { width: 100%; }
.skeleton-line.w-90 { width: 90%; }
.skeleton-line.w-80 { width: 80%; }
.skeleton-line.w-70 { width: 70%; }

/* 章节内容 */
.chapter-content {
  max-width: 68ch;
  margin: 0 auto;
  width: 100%;
}

.summary-pill {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  background: linear-gradient(135deg, rgba(255, 143, 177, 0.15), rgba(139, 92, 246, 0.1));
  border: 1px solid var(--color-sakura);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  animation: fadeIn 400ms var(--ease-spring);
}
.summary-pill i {
  font-size: 18px;
  color: var(--color-sakura);
  flex-shrink: 0;
  margin-top: 1px;
}
.summary-pill strong {
  color: var(--color-text-primary);
}

.chapter-title {
  font-family: var(--font-display);
  font-size: var(--text-3xl);
  font-weight: 700;
  color: var(--color-sakura);
  margin-top: var(--space-3);
}

.chapter-meta {
  display: flex;
  flex-direction: row;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  align-items: center;
}
.chapter-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.chapter-meta i { font-size: 14px; }

.prose pre {
  font-family: var(--font-reader);
  font-size: var(--text-lg);
  line-height: 1.9;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: var(--space-4) 0 0;
}

/* 章尾 */
.chapter-tail {
  padding: var(--space-6) var(--space-5);
  border-radius: var(--radius-md);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(12px);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  margin-top: var(--space-5);
}
.tail-label {
  font-family: var(--font-display);
  font-size: var(--text-lg);
  color: var(--color-text-secondary);
}

/* ===== 底部干预栏 ===== */
.intervention-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 50;
  background: rgba(18, 10, 38, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 1px solid var(--glass-border);
}

.bar-collapsed {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-5);
  max-width: 1280px;
  margin: 0 auto;
}
.bar-icon {
  font-size: 20px;
  color: var(--color-sakura);
  flex-shrink: 0;
}
.bar-input {
  flex: 1;
  height: 40px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-full);
  padding: 0 var(--space-4);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-spring), box-shadow var(--dur-fast) var(--ease-spring);
}
.bar-input:focus {
  border-color: var(--color-sakura);
  box-shadow: 0 0 0 3px rgba(255, 143, 177, 0.15);
}
.bar-input::placeholder { color: var(--color-text-tertiary); }

.bar-submit {
  padding: 8px 20px;
  background: linear-gradient(135deg, var(--color-violet), var(--color-sakura));
  border: none;
  border-radius: var(--radius-full);
  color: #fff;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--dur-fast);
  white-space: nowrap;
  flex-shrink: 0;
}
.bar-submit:hover:not(:disabled) { box-shadow: var(--glow-sakura); }
.bar-submit:active:not(:disabled) { transform: scale(0.96); }
.bar-submit:disabled { opacity: 0.4; cursor: not-allowed; }

.bar-feedback {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: rgba(74, 222, 128, 0.2);
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  animation: fadeIn 250ms var(--ease-spring);
}
.bar-feedback i { font-size: 16px; color: var(--color-success); }

.bar-expand {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background var(--dur-fast);
}
.bar-expand:hover { background: var(--glass-bg-hover); }
.bar-expand i { font-size: 16px; color: var(--color-text-secondary); }

/* 展开态 */
.bar-expanded {
  padding: var(--space-4) var(--space-5);
  max-width: 1280px;
  margin: 0 auto;
}
.bar-expanded-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.bar-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-base);
  color: var(--color-sakura);
  font-weight: 600;
}
.bar-title i { font-size: 18px; }
.bar-collapse {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--dur-fast);
}
.bar-collapse:hover { background: var(--glass-bg-hover); }
.bar-collapse i { font-size: 16px; color: var(--color-text-secondary); }

.bar-expanded-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.bar-textarea {
  width: 100%;
  resize: vertical;
  min-height: 80px;
  font-size: var(--text-sm);
  line-height: 1.6;
  background: var(--color-bg-elevated);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  color: var(--color-text-primary);
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-spring), box-shadow var(--dur-fast) var(--ease-spring);
}
.bar-textarea:focus {
  border-color: var(--color-sakura);
  box-shadow: 0 0 0 3px rgba(255, 143, 177, 0.15);
}
.bar-textarea::placeholder { color: var(--color-text-tertiary); }

.bar-expanded-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.bar-feedback-text {
  font-size: var(--text-xs);
  color: var(--color-success);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  animation: fadeIn 250ms var(--ease-spring);
}
.bar-hint {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  margin-left: auto;
}

/* bar 切换动画 */
.bar-swap-enter-active, .bar-swap-leave-active {
  transition: opacity 150ms var(--ease-out);
}
.bar-swap-enter-from, .bar-swap-leave-to {
  opacity: 0;
}

/* ===== Drawer ===== */
.drawer {
  position: fixed;
  top: 0; right: 0; bottom: 0;
  width: 360px;
  background: rgba(18, 10, 38, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-left: 1px solid var(--glass-border);
  z-index: 200;
  display: flex;
  flex-direction: column;
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) var(--space-5);
  border-bottom: 1px solid var(--glass-border);
}
.drawer-header h2 {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  margin: 0;
}
.drawer-close {
  width: 36px; height: 36px;
  border-radius: var(--radius-full);
  background: var(--glass-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--dur-base) var(--ease-spring);
}
.drawer-close:hover { background: var(--glass-bg-hover); }
.drawer-close i { font-size: 18px; }

.drawer-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-3);
}
.drawer-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--dur-base) var(--ease-spring);
  margin-bottom: 4px;
}
.drawer-item:hover {
  background: var(--glass-bg-hover);
}
.drawer-item.active {
  background: var(--glass-bg-active);
  color: var(--color-sakura);
}
.drawer-num {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}
.drawer-title {
  font-size: var(--text-sm);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.slide-enter-active, .slide-leave-active {
  transition: transform 300ms var(--ease-spring);
}
.slide-enter-from, .slide-leave-to {
  transform: translateX(100%);
}

@media (prefers-reduced-motion: reduce) {
  .reader-header, .left-col, .center-col { animation: none; opacity: 1; }
  .slide-enter-active, .slide-leave-active { transition: opacity 200ms; }
  .slide-enter-from, .slide-leave-to { transform: none; }
  .skeleton-line { animation: none; }
}
@media (max-width: 1024px) {
  .reader-body { grid-template-columns: 1fr; }
  .left-col { position: static; flex-direction: row; flex-wrap: wrap; align-items: center; }
  .left-col .cover-thumb { width: 64px; height: 64px; aspect-ratio: auto; }
  .left-col .nav-btn { width: auto; }
  .left-col .progress-bar { flex: 1; min-width: 100px; }
  .left-col .btn-generate { width: auto; }
}
@media (max-width: 640px) {
  .header-content { flex-wrap: wrap; gap: var(--space-2); }
  .reader-title { font-size: var(--text-base); flex-basis: 100%; order: 5; }
  .prose pre { font-size: var(--text-base); }
  .chapter-title { font-size: var(--text-2xl); }
  .bar-collapsed { padding: var(--space-2) var(--space-3); }
}
</style>
