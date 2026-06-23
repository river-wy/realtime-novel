<!--
  Onboarding 5 步引导（v0.5 + m-v0.5-onboarding 拍板修复版）

  拍板流程:
    Step 1: 必选标签 (题材/风格/基调) → HTTP POST /onboarding step=1
    Step 2: 视觉色调 (UI 主题, 不影响世界树) → HTTP POST /onboarding step=2
    Step 3: 故事大纲 (Agent 引导式 WS) → WS /api/chat onboarding_request_proposal + confirm
    Step 4: 大纲初稿 (Agent 引导式 WS) → WS /api/chat onboarding_request_proposal + confirm
    Step 5: 生成第 1 章 (大按钮 + spinner) → HTTP POST /onboarding step=5

  v0.6 拍板修复:
    - palette 移出 7 件基座 (只存 projects.palette)
    - Step 3-4 不再是用户填 4+4 textarea, 改为 WS 聊天界面
    - LLM 引导式提议 + 用户确认 + 写 7 件
-->
<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { onboardingStep } from '@/api/actions'
import { createProject } from '@/api/projects'
import { useProjectsStore } from '@/stores/projects'
import { useOnboardingChat } from '@/composables/useOnboardingChat'

const router = useRouter()
const route = useRoute()
const projectsStore = useProjectsStore()

const projectId = ref<string>('')  // v0.8.3: 可能从 query.projectId 续接
const currentStep = ref<1 | 2 | 3 | 4 | 5>(1)  // v0.8.3: 可能从 query.step 续接
const loading = ref(false)
const error = ref<string | null>(null)

// ============ Step 1 数据 (v0.8.3: 新增项目名输入) ============
const projectName = ref<string>('')  // 用户填的项目名 (人类可读, 必填)
const genres = ref<string[]>([])
const styles = ref<string[]>([])
const tone = ref<string[]>([])

// ============ Step 2 数据 ============
// v0.7: 视觉色调改为单选（一个项目对应一个主题色）
const palette = ref<string | null>(null)

/** 单选: 点击同一项则取消选中，点击其他项则切换 */
function selectPalette(p: string) {
  palette.value = palette.value === p ? null : p
}

// ============ Step 3/4 WS 聊天 ============
const chat = useOnboardingChat(() => projectId.value)
const userInput = ref('')
const chatContainer = ref<HTMLElement | null>(null)

/** Step 3 字段展示顺序 (v0.7: 3 字段 故事引擎) */
const STEP3_FIELDS = [
  { key: 'story_core', label: '故事内核', sublabel: '主角是谁 + 场景环境 + 要做什么 + 遇到什么意外 + 留悬念 (100+ 章体量)', placeholder: 'Agent 会基于你的输入生成故事大纲' },
  { key: 'characters', label: '主要角色', sublabel: '主角 / 对手 / 盟友，每行「名字 - 身份/角色 - 特点/目的」', placeholder: 'Agent 会基于你的输入生成故事大纲' },
  { key: 'opening_scene', label: '开篇场景', sublabel: '第一章发生的具体场景 + 主角那一刻的不可逆选择', placeholder: 'Agent 会基于你的输入生成故事大纲' },
] as const

/** Step 4 字段展示顺序 (v0.7: 4 字段 大纲细化) */
const STEP4_FIELDS = [
  { key: 'main_arc', label: '主线节点', sublabel: '3-5 个剧情转折，每行 1 个', placeholder: 'Agent 会基于前 3 步信息进一步细化大纲' },
  { key: 'sub_plots', label: '支线', sublabel: '与主线交织但不喧宾夺主的副线，每行 1 个', placeholder: 'Agent 会基于前 3 步信息进一步细化大纲' },
  { key: 'seeds', label: '种子 / 钩子', sublabel: '第 1 章埋下，N 章后亮出来', placeholder: 'Agent 会基于前 3 步信息进一步细化大纲' },
  { key: 'reader_feeling', label: '读者情绪', sublabel: '希望读者合上书那一刻心里留下什么', placeholder: 'Agent 会基于前 3 步信息进一步细化大纲' },
] as const

const currentFields = computed(() =>
  currentStep.value === 3 ? STEP3_FIELDS : currentStep.value === 4 ? STEP4_FIELDS : [],
)

// ============ 选项定义 ============

const PALETTE_OPTIONS = [
  '樱色夜空', '暗夜星辰', '紫水晶',
  '晨光金黄', '雪国白', '春樱粉',
  '墨青山水', '古风竹青', '丹青水墨',
  '赛博朋克', '蒸汽黄铜', '霓虹都市',
  '暮蓝海', '苍绿森林', '秋叶橙',
  '赤红朱砂', '焦橙火光', '落日金',
  '迷幻粉紫', '极光绿', '银河蓝',
]

const GENRE_OPTIONS = [
  '都市', '古风', '玄幻', '修仙', '校园', '职场', '家庭', '悬疑', '科幻',
  '重生', '穿越', '末世', '系统', '无限流', '无敌流', '游戏',
  '奇幻', '武侠', '军旅', '历史', '商战', '电竞', '克苏鲁', '赛博朋克', '蒸汽朋克',
  '轻小说', '二次元', '异能', '灵异', '仙侠',
]

const STYLE_OPTIONS = [
  '言情', '治愈', '悬疑', '战斗', '成长', '日常', '群像', '单女主', '双女主', '慢热', '快节奏', '成人向',
  '脑洞', '热血', '杀伐果断', '扮猪吃虎', '高智商', '烧脑',
  '暗黑', '爽文', '轻松', '搞笑', '腹黑', '逆袭', '甜文', '虐心', '唯美', '史诗', '硬核',
  '吐槽', '毒舌', '中二', '无厘头',
]

const TONE_OPTIONS = [
  '压抑', '温暖', '残酷', '治愈', '戏谑', '冷叙述', '史诗',
  '爽文', '搞笑', '腹黑', '逆袭', '轻松',
  '黑暗', '绝望', '热血', '紧张', '浪漫', '温馨', '沉重', '辛辣', '讽刺',
]

function toggle(arr: string[], value: string) {
  const idx = arr.indexOf(value)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(value)
}

// ============ 项目初始化 ============

async function ensureProject() {
  if (projectId.value) return
  // v0.8.3: 项目名非必填, 不填时用占位名, 后端返回 projectId 后再回填
  const name = projectName.value.trim() || '未命名世界'
  const r = await createProject(name, '')
  projectId.value = r.id
  // 加载项目名 (供其他 step 显示)
  try {
    const detail = await import('@/api/projects').then(m => m.getProject(r.id))
    projectName.value = detail.name
  } catch { /* ignore */ }
}

// ============ v0.8.3: 续接逻辑 (从 query 读 projectId + step) ============

onMounted(() => {
  const qProjectId = route.query.projectId as string | undefined
  const qStep = route.query.step as string | undefined
  if (qProjectId && qStep) {
    // 续接: 跳到指定 step
    projectId.value = qProjectId
    currentStep.value = Math.min(Math.max(parseInt(qStep) || 1, 1), 5) as 1 | 2 | 3 | 4 | 5
    // 加载项目名 (显示用)
    import('@/api/projects').then(m => m.getProject(qProjectId)).then(d => {
      projectName.value = d.name
      if (currentStep.value === 3 || currentStep.value === 4) {
        // Step 3+ 是 WS, 要 open chat
        chat.open(currentStep.value)
      }
    }).catch(() => {})
  }
})

// ============ Step 1-2 HTTP POST ============

async function nextFromHttpStep() {
  loading.value = true
  error.value = null
  try {
    if (currentStep.value === 1) {
      // v0.8.3: 项目名非必填, 不填时后端用 projectId 填充
      if (genres.value.length === 0 || styles.value.length === 0 || tone.value.length === 0) {
        error.value = '请完整选择题材、风格、基调（每类至少 1 个）'
        return
      }
      await ensureProject()
      await onboardingStep(projectId.value, '1', {
        genres: genres.value,
        styles: styles.value,
        tone: tone.value,
      })
      currentStep.value = 2
    } else if (currentStep.value === 2) {
      await onboardingStep(projectId.value, '2', {
        palette: palette.value || '',
      })
      currentStep.value = 3
      // 进入 Step 3: 打开 WS 连接
      chat.open(3)
    }
  } catch (e: any) {
    error.value = e.message || '请求失败'
  } finally {
    loading.value = false
  }
}

// ============ Step 3-4 WS 交互 ============

/** "让 Agent 提议" 按钮 */
function handleRequestProposal() {
  chat.requestProposal(userInput.value.trim())
  userInput.value = ''
}

/** 用户发修改意见（按 Enter） */
function handleSendUserMessage() {
  const text = userInput.value.trim()
  if (!text) return
  chat.requestProposal(text)
  userInput.value = ''
}

/** "确认大纲 → 写 7 件" 按钮 */
async function handleConfirm() {
  chat.confirm()
}

/** 监听 stepDone → 自动跳下一步 */
watch(() => chat.stepDone.value, (done) => {
  if (!done) return
  if (currentStep.value === 3) {
    // Step 3 done → Step 4: 先关旧 ws → 切 step → 短暂延迟后开新 ws
    setTimeout(() => {
      chat.close()
      currentStep.value = 4
      setTimeout(() => chat.open(4), 100)
    }, 1500)  // 给用户时间看到 "Step 3 完成" 提示
  } else if (currentStep.value === 4) {
    // Step 4 done → Step 5
    setTimeout(() => {
      currentStep.value = 5
      chat.close()
    }, 1500)
  }
})

// 监听 chat messages → 滚到底
watch(() => chat.messages.value.length, async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
})

// ============ Step 5 章节生成 ============

async function generateChapter() {
  loading.value = true
  error.value = null
  try {
    await onboardingStep(projectId.value, '5', {})
    await projectsStore.loadList()
    router.push({ name: 'reader', params: { projectId: projectId.value, chapterNum: 1 } })
  } catch (e: any) {
    error.value = e.message || '章节生成失败'
  } finally {
    loading.value = false
  }
}

// ============ 工具 ============

function getStepTitle(step: number): string {
  return ['', '必选标签', '视觉色调', '大纲生成', '大纲细化', '生成第 1 章'][step]
}

function getStepHint(step: number): string {
  return [
    '',
    '题材 / 风格 / 基调（每类至少 1 个）',
    '选一个喜欢的色调（影响 UI 主题，不影响世界树）',
    '让 Agent 帮你生成故事大纲',
    '让 Agent 帮你进一步细化大纲',
    'AI 会读取前 4 步的所有信息生成第 1 章',
  ][step]
}
</script>

<template>
  <div class="onboarding">
    <!-- 步骤指示器 -->
    <div class="step-indicator">
      <div
        v-for="s in [1, 2, 3, 4, 5]"
        :key="s"
        class="step-dot"
        :class="{
          active: s === currentStep,
          done: s < currentStep,
        }"
      >
        <span v-if="s < currentStep">✓</span>
        <span v-else>{{ s }}</span>
      </div>
    </div>

    <!-- 步骤标题 -->
    <header class="step-header">
      <h1>📌 Step {{ currentStep }} · {{ getStepTitle(currentStep) }}</h1>
      <p class="hint">{{ getStepHint(currentStep) }}</p>
    </header>

    <!-- ============== Step 1 ============== -->
    <section v-if="currentStep === 1" class="step fade-in">
      <div class="project-name-input">
        <label for="project-name">🌍 给你的世界起个临时名（选填，Step 4 后会被 LLM 自动改）</label>
        <input
          id="project-name"
          v-model="projectName"
          type="text"
          maxlength="50"
          placeholder="不填会自动用项目 ID 占位"
          :disabled="!!projectId"
        />
        <p class="hint">这是占位名，Step 4 大纲完成后 LLM 会根据故事核心重新起名</p>
      </div>
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

    <!-- ============== Step 2 ============== -->
    <section v-else-if="currentStep === 2" class="step fade-in">
      <div class="tag-grid">
        <button
          v-for="p in PALETTE_OPTIONS"
          :key="p"
          class="tag tag-palette"
          :class="{ selected: palette === p }"
          @click="selectPalette(p)"
        >{{ p }}</button>
      </div>
      <p class="palette-note">
        💡 提示：视觉色调仅影响阅读页 UI 主题，<strong>不影响</strong>故事的世界树 / 情节 / 角色。
      </p>
    </section>

    <!-- ============== Step 3-4 WS 聊天界面 ============== -->
    <section v-else-if="currentStep === 3 || currentStep === 4" class="step chat-layout fade-in">
      <!-- 左：对话消息流 -->
      <div class="chat-pane">
        <div class="chat-header">
          <span class="chat-status" :class="{ connected: chat.connected.value }">
            {{ chat.connecting.value ? '连接中...' : chat.connected.value ? '● 已连接' : '○ 未连接' }}
          </span>
        </div>
        <div ref="chatContainer" class="chat-messages">
          <div
            v-for="(m, idx) in chat.messages.value"
            :key="idx"
            class="chat-msg"
            :class="['role-' + m.role, { thinking: m.thinking }]"
          >
            <div class="chat-avatar">
              {{ m.role === 'user' ? '我' : m.role === 'agent' ? 'AI' : 'sys' }}
            </div>
            <div class="chat-bubble">
              <div v-if="m.thinking && chat.thinking.value" class="thinking-dots">
                <span></span><span></span><span></span>
              </div>
              <pre v-else>{{ m.content }}</pre>
            </div>
          </div>
        </div>
        <div class="chat-input-row">
          <input
            v-model="userInput"
            class="chat-input"
            type="text"
            placeholder="告诉 Agent 你的修改意见（如：'更黑暗一点' '主角是女性'）"
            :disabled="!chat.connected.value || chat.thinking.value"
            @keydown.enter="handleSendUserMessage"
          />
          <button
            class="btn btn-secondary"
            :disabled="!chat.connected.value || chat.thinking.value"
            @click="handleSendUserMessage"
          >发送</button>
        </div>
      </div>

      <!-- 右：故事大纲展示框 -->
      <div class="fields-pane">
        <div class="fields-header">
          <h3>📋 {{ currentStep === 3 ? 'Step 3 · 故事大纲' : 'Step 4 · 大纲细化' }}</h3>
          <p class="fields-hint">点下方「让 Agent 提议」生成大纲，再「确认大纲」写入 7 件基座</p>
        </div>
        <div class="fields-list">
          <div
            v-for="f in currentFields"
            :key="f.key"
            class="field-card"
            :class="{ filled: chat.fields.value[f.key] }"
          >
            <div class="field-label-row">
              <label class="field-label">{{ f.label }}</label>
              <span v-if="f.sublabel" class="field-sublabel">{{ f.sublabel }}</span>
            </div>
            <div v-if="chat.fields.value[f.key]" class="field-value">
              <pre>{{ chat.fields.value[f.key] }}</pre>
            </div>
            <div v-else class="field-empty">
              <span class="placeholder">{{ f.placeholder }}</span>
            </div>
          </div>
        </div>
        <div class="fields-actions">
          <button
            class="btn btn-primary btn-large"
            :disabled="!chat.connected.value || chat.thinking.value"
            @click="handleRequestProposal"
          >
            <span v-if="chat.thinking.value" class="spinner-inline"></span>
            {{ chat.thinking.value ? 'Agent 思考中...' : (chat.hasFields.value ? '🔄 让 Agent 重新提议' : '✨ 让 Agent 提议') }}
          </button>
          <button
            class="btn btn-success btn-large"
            :disabled="!chat.hasFields.value || chat.thinking.value || chat.stepDone.value"
            @click="handleConfirm"
          >
            {{ chat.stepDone.value ? '✅ 已写入 7 件' : '✅ 确认大纲 → 写 7 件' }}
          </button>
        </div>
      </div>
    </section>

    <!-- ============== Step 5 章节生成 ============== -->
    <section v-else-if="currentStep === 5" class="step fade-in">
      <div class="generate-card">
        <h2>🎬 准备生成第 1 章</h2>
        <p>AI 会读取 Step 1-4 的所有信息（题材 / 风格 / 基调 / 故事大纲），生成第 1 章 + 摘要。</p>
        <p class="time-hint">预计耗时 30-60 秒</p>
        <div v-if="loading" class="generating">
          <div class="spinner"></div>
          <span>AI 正在生成 7 件 + 第 1 章...</span>
        </div>
        <button
          v-else
          class="btn btn-primary btn-huge"
          @click="generateChapter"
        >
          🚀 开始生成
        </button>
      </div>
    </section>

    <!-- 错误展示 -->
    <div v-if="error || chat.error.value" class="error">
      {{ error || chat.error.value }}
    </div>

    <!-- Step 1-2 的 "下一步" 按钮 -->
    <div v-if="currentStep === 1 || currentStep === 2" class="actions">
      <button
        class="btn btn-primary"
        @click="nextFromHttpStep"
        :disabled="loading || (currentStep === 2 && !palette)"
      >
        {{ loading ? '处理中...' : '下一步 →' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.onboarding {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--space-6);
}

/* ============ 步骤指示器 ============ */
.step-indicator {
  display: flex;
  gap: var(--space-2);
  justify-content: center;
  margin-bottom: var(--space-6);
}

/* v0.8.3: Step 1 项目名输入框 */
.project-name-input {
  margin-bottom: var(--space-6);
  padding: var(--space-4);
  background: var(--color-night-1);
  border: 1px solid var(--color-night-3);
  border-radius: var(--radius-md);
}
.project-name-input label {
  display: block;
  font-size: var(--text-md);
  font-weight: 600;
  margin-bottom: var(--space-2);
  color: var(--color-text);
}
.project-name-input input {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-md);
  background: var(--color-night-2);
  border: 1px solid var(--color-night-3);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-family: inherit;
  transition: border-color 0.2s;
}
.project-name-input input:focus {
  outline: none;
  border-color: var(--color-accent-1);
  box-shadow: var(--shadow-glow);
}
.project-name-input input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.project-name-input .hint {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-dim);
}
.step-dot {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--color-night-2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-sm);
  color: var(--color-text-dim);
  border: 2px solid transparent;
  font-weight: 600;
}
.step-dot.active {
  background: var(--color-accent-1);
  color: white;
  border-color: var(--color-accent-2);
  box-shadow: var(--shadow-glow);
}
.step-dot.done {
  background: var(--color-accent-3);
  color: white;
}

.step-header {
  text-align: center;
  margin-bottom: var(--space-5);
}
.step-header h1 {
  font-size: var(--text-2xl);
  margin-bottom: var(--space-2);
  color: var(--color-accent-1);
}
.hint {
  color: var(--color-text-faint);
  font-size: var(--text-sm);
}

/* ============ Step 1/2 通用 ============ */
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
  color: var(--color-text);
  transition: all var(--motion-fast) var(--ease-out);
  cursor: pointer;
}
.tag:hover {
  border-color: var(--color-accent-1);
}
.tag.selected {
  background: var(--color-accent-1);
  color: white;
  border-color: var(--color-accent-1);
}
.tag-palette.selected {
  background: linear-gradient(135deg, var(--color-accent-1), var(--color-accent-3));
}
.palette-note {
  margin-top: var(--space-4);
  padding: var(--space-3);
  background: rgba(196, 181, 253, 0.08);
  border-left: 3px solid var(--color-accent-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  color: var(--color-text-dim);
}

/* ============ Step 3-4 聊天布局 ============ */
.chat-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
  min-height: 540px;
}

@media (max-width: 900px) {
  .chat-layout {
    grid-template-columns: 1fr;
  }
}

/* 左：对话消息流 */
.chat-pane {
  display: flex;
  flex-direction: column;
  background: var(--color-night-1);
  border: 1px solid var(--color-night-3);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.chat-header {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-night-3);
  background: var(--color-night-2);
}
.chat-status {
  font-size: var(--text-xs);
  color: var(--color-error);
}
.chat-status.connected {
  color: var(--color-accent-3);
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-height: 360px;
  max-height: 480px;
}
.chat-msg {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  animation: fade-in-up 0.3s var(--ease-out);
}
.chat-msg.role-user {
  flex-direction: row-reverse;
}
.chat-avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-accent-1);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  font-weight: 600;
}
.chat-msg.role-user .chat-avatar {
  background: var(--color-accent-3);
}
.chat-msg.role-system .chat-avatar {
  background: var(--color-night-3);
  color: var(--color-text-faint);
}
.chat-bubble {
  max-width: 80%;
  padding: var(--space-3) var(--space-4);
  background: var(--color-night-2);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  line-height: 1.6;
}
.chat-msg.role-user .chat-bubble {
  background: var(--color-accent-1);
  color: white;
}
.chat-bubble pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-body);
}
.thinking-dots {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}
.thinking-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-accent-2);
  animation: bounce 1.4s infinite;
}
.thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.7); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
.chat-input-row {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-3);
  border-top: 1px solid var(--color-night-3);
  background: var(--color-night-2);
}
.chat-input {
  flex: 1;
  padding: var(--space-3) var(--space-4);
  background: var(--color-night-1);
  border: 1px solid var(--color-night-3);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: var(--text-sm);
  font-family: var(--font-body);
}
.chat-input:focus {
  outline: none;
  border-color: var(--color-accent-1);
}
.chat-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 右：故事大纲展示框 */
.fields-pane {
  display: flex;
  flex-direction: column;
  background: var(--color-night-1);
  border: 1px solid var(--color-night-3);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.fields-header {
  padding: var(--space-4);
  border-bottom: 1px solid var(--color-night-3);
  background: var(--color-night-2);
}
.fields-header h3 {
  font-size: var(--text-base);
  margin-bottom: var(--space-1);
  color: var(--color-accent-2);
}
.fields-hint {
  font-size: var(--text-xs);
  color: var(--color-text-faint);
}
.fields-list {
  flex: 1;
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  overflow-y: auto;
  min-height: 280px;
  max-height: 360px;
}
.field-card {
  padding: var(--space-3);
  border: 1px solid var(--color-night-3);
  border-radius: var(--radius-md);
  background: var(--color-night-2);
  transition: all var(--motion-fast) var(--ease-out);
}
.field-card.filled {
  border-color: var(--color-accent-3);
  background: rgba(196, 181, 253, 0.05);
}
.field-card label {
  display: block;
  font-size: var(--text-xs);
  color: var(--color-text-dim);
  margin-bottom: var(--space-2);
  font-weight: 500;
}
.field-card.filled label {
  color: var(--color-accent-3);
}
/* v0.8.3: 字段 label + sublabel 并排 */
.field-label-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}
.field-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-accent-3);
  margin-bottom: 0 !important;
}
.field-sublabel {
  font-size: var(--text-xs);
  color: var(--color-text-dim);
  line-height: 1.4;
}
.field-value pre {
  margin: 0;
  font-family: var(--font-body);
  font-size: var(--text-sm);
  line-height: 1.6;
  color: var(--color-text);
  white-space: pre-wrap;
  word-break: break-word;
}
.field-empty {
  font-size: var(--text-xs);
  color: var(--color-text-faint);
  font-style: italic;
}
.field-empty .placeholder {
  opacity: 0.5;
}
.fields-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  border-top: 1px solid var(--color-night-3);
  background: var(--color-night-2);
}

/* ============ Step 5 ============ */
.generate-card {
  text-align: center;
  padding: var(--space-7);
  background: var(--color-night-1);
  border: 1px solid var(--color-night-3);
  border-radius: var(--radius-lg);
  max-width: 600px;
  margin: 0 auto;
}
.generate-card h2 {
  font-size: var(--text-xl);
  margin-bottom: var(--space-3);
  color: var(--color-accent-1);
}
.generate-card p {
  color: var(--color-text-dim);
  margin-bottom: var(--space-3);
}
.time-hint {
  font-size: var(--text-sm);
  color: var(--color-text-faint);
}
.btn-huge {
  font-size: var(--text-lg);
  padding: var(--space-5) var(--space-8);
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

/* ============ 通用按钮 ============ */
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
  cursor: pointer;
  border: none;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-primary {
  background: linear-gradient(135deg, var(--color-accent-1), var(--color-accent-3));
  color: white;
  box-shadow: var(--shadow-glow);
}
.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
}
.btn-secondary {
  background: var(--color-night-3);
  color: var(--color-text);
}
.btn-secondary:hover:not(:disabled) {
  background: var(--color-night-2);
}
.btn-success {
  background: linear-gradient(135deg, #4ade80, #22c55e);
  color: white;
}
.btn-success:hover:not(:disabled) {
  transform: translateY(-2px);
}
.btn-large {
  font-size: var(--text-base);
  padding: var(--space-3) var(--space-5);
}

.spinner-inline {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-night-3);
  border-top-color: var(--color-accent-1);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  vertical-align: middle;
  margin-right: var(--space-2);
}

/* ============ 错误 ============ */
.error {
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid var(--color-error);
  color: var(--color-error);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  margin-top: var(--space-4);
  text-align: center;
}

/* ============ 动画 ============ */
@keyframes spin {
  to { transform: rotate(360deg); }
}
@keyframes fade-in-up {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.fade-in {
  animation: fade-in-up 0.4s var(--ease-out);
}
</style>