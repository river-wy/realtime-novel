<script setup lang="ts">
/**
 * Onboarding 5 步引导（v0.5 接入后端）
 *
 * Step 1: 必选标签 (题材/风格/基调)
 * Step 2: 调色板 (装饰性偏好)
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
const currentStep = ref<OnboardingStep>('1')
const loading = ref(false)
const error = ref<string | null>(null)

// Step 1 数据
const genres = ref<string[]>([])
const styles = ref<string[]>([])
const tone = ref<string[]>([])

// Step 2 数据 — 视觉色调偏好（v0.6 重构：不再复用 STYLE_OPTIONS）
const palette = ref<string[]>([])

// 视觉色调选项（v0.6 新增：真正的"调色板"，影响后续生成图片/UI 主题）
const PALETTE_OPTIONS = [
  // 暗紫调（项目主色）
  '樱色夜空', '暗夜星辰', '紫水晶',
  // 明亮调
  '晨光金黄', '雪国白', '春樱粉',
  // 古风调
  '墨青山水', '古风竹青', '丹青水墨',
  // 赛博/工业调
  '赛博朋克', '蒸汽黄铜', '霓虹都市',
  // 自然调
  '暮蓝海', '苍绿森林', '秋叶橙',
  // 暖色调
  '赤红朱砂', '焦橙火光', '落日金',
  // 柔和调
  '迷幻粉紫', '极光绿', '银河蓝',
]

// 题材（欧尼酱指定 + 补充）
const GENRE_OPTIONS = [
  // 原有
  '都市', '古风', '玄幻', '修仙', '校园', '职场', '家庭', '悬疑', '科幻',
  // 新增
  '重生', '穿越', '末世', '系统', '无限流', '无敌流', '游戏',
  '奇幻', '武侠', '军旅', '历史', '商战', '电竞', '克苏鲁', '赛博朋克', '蒸汽朋克',
  '轻小说', '二次元', '异能', '灵异', '仙侠',
]

// 风格（欧尼酱指定 + 补充）
const STYLE_OPTIONS = [
  // 原有
  '言情', '治愈', '悬疑', '战斗', '成长', '日常', '群像', '单女主', '双女主', '慢热', '快节奏', '成人向',
  // 新增
  '脑洞', '热血', '杀伐果断', '扮猪吃虎', '高智商', '烧脑',
  '暗黑', '爽文', '轻松', '搞笑', '腹黑', '逆袭', '甜文', '虐心', '唯美', '史诗', '硬核',
  '吐槽', '毒舌', '中二', '无厘头',
]

// 基调（欧尼酱指定 + 补充）
const TONE_OPTIONS = [
  // 原有
  '压抑', '温暖', '残酷', '治愈', '戏谑', '冷叙述', '史诗',
  // 新增
  '爽文', '搞笑', '腹黑', '逆袭', '轻松',
  '黑暗', '绝望', '热血', '紧张', '浪漫', '温馨', '沉重', '辛辣', '讽刺',
]

/**
 * 切换数组元素的选中状态
 * 收 Ref<string[]>，函数内用 .value 触发响应式更新
 * 模板里调用：@click="toggle(genres, g)" — Vue 会把 genres 自动解包成 string[] 传入，
 *  所以这里要特别处理：用 lambda 包裹显式传 ref 引用，或函数内部重新取 .value
 *
 * 当前实现：函数接受 string[]（Vue 解包后的值），splice/push 会修改原数组
 * （原数组是 ref.value 的引用，splice/push 会修改 ref.value 指向的数组 → 响应式触发 ✓）
 * — Vue 3 Proxy-based reactivity 能追踪数组方法调用 (push/pop/splice/shift 等)
 */
function toggle(arr: string[], value: string) {
  const idx = arr.indexOf(value)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(value)
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
    if (currentStep.value === '1') {
      if (genres.value.length === 0 || styles.value.length === 0 || tone.value.length === 0) {
        error.value = '请完整选择题材、风格、基调（至少 1 个）'
        return
      }
      await ensureProject()
      await onboardingStep(projectId.value, '1', {
        genres: genres.value, styles: styles.value, tone: tone.value.join(',')  // 数组转字符串给 LLM prompt
      })
      currentStep.value = '2'
    } else if (currentStep.value === '2') {
      await onboardingStep(projectId.value, '2', { palette: palette.value })
      currentStep.value = '3'
    } else if (currentStep.value === '3') {
      await onboardingStep(projectId.value, '3', { /* payload */ })
      currentStep.value = '4'
    } else if (currentStep.value === '4') {
      await onboardingStep(projectId.value, '4', { /* payload */ })
      currentStep.value = '5'
    } else if (currentStep.value === '5') {
      // Step 5: 后台准备 + 生成第 1 章
      await onboardingStep(projectId.value, '5', {})
      await chaptersStore.generate(projectId.value)
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
        v-for="s in ['1', '2', '3', '4', '5']"
        :key="s"
        class="step-dot"
        :class="{ active: s === currentStep, done: ['1','2','3','4','5'].indexOf(s) < ['1','2','3','4','5'].indexOf(currentStep) }"
      >{{ s }}</div>
    </div>

    <!-- Step 1 -->
    <section v-if="currentStep === '1'" class="step fade-in">
      <h1>📌 Step 1 · 必选标签</h1>
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
          :class="{ selected: tone.includes(t) }"
          @click="toggle(tone, t)"
        >{{ t }}</button>
      </div>
    </section>

    <!-- Step 2 -->
    <section v-else-if="currentStep === '2'" class="step fade-in">
      <h1>📌 Step 2 · 视觉色调</h1>
      <p>选几个喜欢的色调（影响后续图片生成 + UI 主题）</p>
      <div class="tag-grid">
        <button
          v-for="p in PALETTE_OPTIONS"
          :key="p"
          class="tag"
          :class="{ selected: palette.includes(p) }"
          @click="toggle(palette, p)"
        >{{ p }}</button>
      </div>
    </section>

    <!-- Step 3/4 占位 -->
    <section v-else-if="currentStep === '3' || currentStep === '4'" class="step fade-in">
      <h1>📌 Step {{ currentStep }}</h1>
      <p>引导式自由文本（v0.6 详细设计）</p>
      <p class="hint">本阶段引导内容待 v0.5.1 补充</p>
    </section>

    <!-- Step 5 后台准备 + 生成章节 -->
    <section v-else-if="currentStep === '5'" class="step fade-in">
      <h1>🛠 Step 5 · 后台准备</h1>
      <p>AI 正在生成 7 件基座 + 第 1 章...</p>
      <div v-if="loading" class="generating">
        <div class="spinner"></div>
        <span>30-60s</span>
      </div>
      <p v-else-if="!error" class="hint">点击下一步开始生成</p>
    </section>

    <div v-if="error" class="error">{{ error }}</div>

    <div class="actions" v-if="!['5'].includes(currentStep)">
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
