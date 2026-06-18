<script setup lang="ts">
/**
 * Onboarding 5 步引导（v0.5 接入后端）
 *
 * Step 1a: 必选标签 (题材/风格/基调)
 * Step 1b: 调色板 (装饰性偏好)
 * Step 2: 引导式自由文本
 * Step 3: 大纲确认
 * Step 4: 后台准备（v0.5 端到端：调 LLM 真实生成 7 件）
 * Step 5: 第 1 章生成 + 跳转阅读
 */
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { onboardingStep, type OnboardingStep } from '@/api/actions'
import { createProject } from '@/api/projects'
import { useProjectsStore } from '@/stores/projects'
import { useChaptersStore } from '@/stores/chapters'

const router = useRouter()
const projectsStore = useProjectsStore()
const chaptersStore = useChaptersStore()

const projectId = ref('')
const currentStep = ref<OnboardingStep>('1a')
const loading = ref(false)
const error = ref<string | null>(null)

// Step 1a 数据
const genres = ref<string[]>([])
const styles = ref<string[]>([])
const tone = ref('')

// Step 1b 数据
const palette = ref<string[]>([])

const GENRE_OPTIONS = ['都市', '古风', '玄幻', '修仙', '校园', '职场', '家庭', '悬疑', '科幻']
const STYLE_OPTIONS = ['言情', '治愈', '悬疑', '战斗', '成长', '日常', '群像', '单女主', '双女主', '慢热', '快节奏', '成人向']
const TONE_OPTIONS = ['压抑', '温暖', '残酷', '治愈', '戏谑', '冷叙述', '史诗']

function toggle(arr: any, value: string) {
  const idx = arr.value.indexOf(value)
  if (idx >= 0) arr.value.splice(idx, 1)
  else arr.value.push(value)
}

async function ensureProject() {
  if (projectId.value) return
  const name = `world-${Date.now().toString(36)}`
  const r = await createProject(name, 'modern')
  projectId.value = r.id
}

async function goNext() {
  loading.value = true
  error.value = null
  try {
    if (currentStep.value === '1a') {
      if (genres.value.length === 0 || styles.value.length === 0 || !tone.value) {
        error.value = '请完整选择题材、风格、基调'
        return
      }
      await ensureProject()
      await onboardingStep(projectId.value, '1a', {
        genres: genres.value, styles: styles.value, tone: tone.value
      })
      currentStep.value = '1b'
    } else if (currentStep.value === '1b') {
      await onboardingStep(projectId.value, '1b', { palette: palette.value })
      currentStep.value = '2'
    } else if (currentStep.value === '2') {
      await onboardingStep(projectId.value, '2', { /* payload */ })
      currentStep.value = '3'
    } else if (currentStep.value === '3') {
      await onboardingStep(projectId.value, '3', { /* payload */ })
      currentStep.value = '4'
    } else if (currentStep.value === '4') {
      // Step 4: 后台准备（生成 7 件）
      await onboardingStep(projectId.value, '4', {})
      // Step 5: 生成第 1 章
      await chaptersStore.generate(projectId.value)
      currentStep.value = '5'
    } else {
      // 完成 → 跳转阅读
      await projectsStore.loadList()
      router.push({ name: 'reader', params: { projectId: projectId.value, chapterNum: 1 } })
    }
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="onboarding">
    <div class="step-indicator">
      <div
        v-for="s in ['1a', '1b', '2', '3', '4', '5']"
        :key="s"
        class="step-dot"
        :class="{ active: s === currentStep, done: ['1a','1b','2','3','4','5'].indexOf(s) < ['1a','1b','2','3','4','5'].indexOf(currentStep) }"
      >{{ s }}</div>
    </div>

    <!-- Step 1a -->
    <section v-if="currentStep === '1a'" class="step fade-in">
      <h1>📌 Step 1a · 必选标签</h1>
      <h3>题材</h3>
      <div class="tag-grid">
        <button
          v-for="g in GENRE_OPTIONS"
          :key="g"
          class="tag"
          :class="{ selected: genres.includes(g) }"
          @click="toggle(genres, g)"
        >{{ g }}</button>
      </div>
      <h3>风格</h3>
      <div class="tag-grid">
        <button
          v-for="s in STYLE_OPTIONS"
          :key="s"
          class="tag"
          :class="{ selected: styles.includes(s) }"
          @click="toggle(styles, s)"
        >{{ s }}</button>
      </div>
      <h3>基调</h3>
      <div class="tag-grid">
        <button
          v-for="t in TONE_OPTIONS"
          :key="t"
          class="tag"
          :class="{ selected: tone === t }"
          @click="tone = t"
        >{{ t }}</button>
      </div>
    </section>

    <!-- Step 1b -->
    <section v-else-if="currentStep === '1b'" class="step fade-in">
      <h1>📌 Step 1b · 调色板</h1>
      <p>装饰性偏好（可跳过）</p>
      <div class="tag-grid">
        <button
          v-for="s in STYLE_OPTIONS"
          :key="s"
          class="tag"
          :class="{ selected: palette.includes(s) }"
          @click="toggle(palette, s)"
        >{{ s }}</button>
      </div>
    </section>

    <!-- Step 2/3 占位 -->
    <section v-else-if="currentStep === '2' || currentStep === '3'" class="step fade-in">
      <h1>📌 Step {{ currentStep }}</h1>
      <p>引导式自由文本（v0.6 详细设计）</p>
      <p class="hint">本阶段引导内容待 v0.5.1 补充</p>
    </section>

    <!-- Step 4 后台准备 -->
    <section v-else-if="currentStep === '4'" class="step fade-in">
      <h1>🛠 Step 4 · 后台准备</h1>
      <p>AI 正在生成 7 件基座 + 第 1 章...</p>
      <div v-if="loading" class="generating">
        <div class="spinner"></div>
        <span>30-60s</span>
      </div>
    </section>

    <!-- Step 5 完成 -->
    <section v-else-if="currentStep === '5'" class="step fade-in">
      <h1>🎉 Step 5 · 完成</h1>
      <p>第 1 章已生成！</p>
      <button class="btn btn-primary" @click="router.push({ name: 'reader', params: { projectId, chapterNum: 1 } })">
        开始阅读 →
      </button>
    </section>

    <div v-if="error" class="error">{{ error }}</div>

    <div class="actions" v-if="!['4', '5'].includes(currentStep)">
      <button class="btn btn-primary" @click="goNext" :disabled="loading">
        {{ loading ? '处理中...' : '下一步 →' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.onboarding {
  max-width: 720px;
  margin: 0 auto;
  padding: var(--space-6);
}

.step-indicator {
  display: flex;
  gap: var(--space-2);
  justify-content: center;
  margin-bottom: var(--space-6);
}

.step-dot {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--color-night-2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  color: var(--color-text-dim);
  border: 2px solid transparent;
}
.step-dot.active {
  background: var(--color-accent-1);
  color: white;
  border-color: var(--color-accent-2);
}
.step-dot.done {
  background: var(--color-accent-3);
  color: white;
}

.step h1 {
  font-size: var(--text-2xl);
  margin-bottom: var(--space-5);
  color: var(--color-accent-1);
}

.step h3 {
  font-size: var(--text-lg);
  margin: var(--space-5) 0 var(--space-3);
  color: var(--color-text-dim);
}

.tag-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.tag {
  padding: var(--space-2) var(--space-4);
  background: var(--color-night-2);
  border: 1px solid var(--color-night-3);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  transition: all var(--motion-fast) var(--ease-out);
}
.tag:hover {
  border-color: var(--color-accent-1);
}
.tag.selected {
  background: var(--color-accent-1);
  color: white;
  border-color: var(--color-accent-1);
}

.hint {
  color: var(--color-text-faint);
  font-size: var(--text-sm);
}

.actions {
  text-align: center;
  margin-top: var(--space-6);
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
.btn-primary:hover:not(:disabled) { transform: translateY(-2px); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.error {
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid var(--color-error);
  color: var(--color-error);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  margin-top: var(--space-4);
}

.generating {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  color: var(--color-accent-2);
  padding: var(--space-5);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-night-3);
  border-top-color: var(--color-accent-1);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
