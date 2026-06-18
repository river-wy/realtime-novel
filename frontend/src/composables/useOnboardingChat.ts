/**
 * useOnboardingChat — Step 3/4 管家 Agent WS 引导式对话
 *
 * v0.5 拍板：Step 3/4 走 WS /api/chat + 管家 Agent（不用 HTTP POST）
 * 设计：
 * - 不复用 conversation store（onboarding 是独立 context, 不污染 user-conv）
 * - 独立 WebSocket 连接到 /api/chat
 * - 事件订阅：agent_thinking / onboarding_proposal / onboarding_confirmed / onboarding_step_done / error
 * - 暴露 messages / fields / streaming / requestProposal / confirm / close
 */
import { ref, computed, onUnmounted } from 'vue'

const WS_BASE = `ws://${window.location.host}/api/chat`

export type OnboardingStepNum = 3 | 4

export interface OnboardingChatMessage {
  role: 'agent' | 'user' | 'system'
  content: string
  /** 是否正在流式接收（agent_thinking） */
  thinking?: boolean
  timestamp: number
}

export function useOnboardingChat(projectId: () => string | null) {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const connecting = ref(false)

  /** 当前 step（3 或 4），决定推哪个 prompt 给 LLM */
  const currentStep = ref<OnboardingStepNum | null>(null)

  /** Agent 提议的 4 字段 */
  const fields = ref<Record<string, string>>({})

  /** 对话历史（Agent 引导语 + 用户修改意见） */
  const messages = ref<OnboardingChatMessage[]>([])

  /** Agent 是否在思考 */
  const thinking = ref(false)

  /** 最近一次错误 */
  const error = ref<string | null>(null)

  /** Step 是否已完成（onboarding_step_done 收到） */
  const stepDone = ref(false)

  function addAgentMessage(content: string, isThinking = false) {
    messages.value.push({
      role: 'agent',
      content,
      thinking: isThinking,
      timestamp: Date.now(),
    })
  }

  function addUserMessage(content: string) {
    messages.value.push({
      role: 'user',
      content,
      timestamp: Date.now(),
    })
  }

  function addSystemMessage(content: string) {
    messages.value.push({
      role: 'system',
      content,
      timestamp: Date.now(),
    })
  }

  function open(step: OnboardingStepNum) {
    if (ws.value && currentStep.value === step) {
      // 已连接同一 step，直接复用
      return
    }
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    connecting.value = true
    error.value = null
    currentStep.value = step
    fields.value = {}
    messages.value = []
    stepDone.value = false

    const socket = new WebSocket(WS_BASE)
    socket.onopen = () => {
      connected.value = true
      connecting.value = false
      addAgentMessage(
        step === 3
          ? '👋 你好！我是你的小说创作引导师。\n\n我已经看过你在 Step 1 选择的题材/风格/基调，也看到了 Step 2 的视觉色调偏好。\n\n点下方「让 Agent 提议」按钮，我会基于这些信息为你生成 Step 3 的 4 个核心设定字段（核心关系 / 情感锚点 / 禁区 / 结局偏好）。生成后你可以随时在输入框里告诉我「改一下 XXX」「更具体」之类的修改意见。'
          : '👋 现在我们进入 Step 4 大纲初稿。\n\nStep 3 的核心设定已经写入 7 件基座。我会基于前 3 步的所有信息，为你生成 4 个大纲字段（主线核心矛盾 / 支线 / 人物 / 种子）。同样可以随时让 Agent 修改。',
      )
    }
    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        handleEvent(msg)
      } catch (e) {
        console.error('[OnboardingChat] WS parse error', e)
      }
    }
    socket.onclose = () => {
      connected.value = false
      ws.value = null
    }
    socket.onerror = () => {
      error.value = 'WebSocket 连接错误'
      connecting.value = false
    }
    ws.value = socket
  }

  function handleEvent(msg: any) {
    const t = msg.type
    if (t === 'agent_thinking') {
      thinking.value = true
      addAgentMessage(msg.content || '思考中...', true)
    } else if (t === 'onboarding_proposal') {
      thinking.value = false
      // 更新最后一条非 thinking 的 agent 消息：标记为最终结果
      fields.value = msg.fields || {}
      addAgentMessage(
        '✅ 已为你生成 4 个字段。点击右下「确认字段 → 写 7 件」按钮，或者继续在输入框告诉我你想调整的方向。',
      )
    } else if (t === 'onboarding_confirmed') {
      thinking.value = false
      addAgentMessage(
        `✅ Step ${msg.step} 字段已写入 7 件基座（${msg.artifacts_written?.join(', ') || ''}）`,
      )
    } else if (t === 'onboarding_step_done') {
      thinking.value = false
      stepDone.value = true
      addAgentMessage(`🎉 Step ${msg.step} 完成，准备进入 Step ${msg.next_step}。`)
    } else if (t === 'error') {
      thinking.value = false
      error.value = msg.message || '未知错误'
      addAgentMessage(`❌ 错误：${msg.message || '未知错误'}`)
    } else {
      // 其它事件（conversation_started 等）忽略
      console.debug('[OnboardingChat] 忽略事件:', t, msg)
    }
  }

  /**
   * 让 Agent 提议 4 字段
   * 首次调用 user_message='', 后续调用传修改意见
   */
  function requestProposal(userMessage = '') {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      error.value = 'WS 未连接'
      return
    }
    const pid = projectId()
    if (!pid || !currentStep.value) {
      error.value = 'project_id 或 step 缺失'
      return
    }
    if (userMessage) {
      addUserMessage(userMessage)
    } else {
      addAgentMessage('🤔 正在为你生成 4 字段...')
    }
    ws.value.send(JSON.stringify({
      type: 'onboarding_request_proposal',
      project_id: pid,
      step: currentStep.value,
      user_message: userMessage,
      current_fields: { ...fields.value },
    }))
  }

  /**
   * 用户确认 4 字段 → 写 7 件
   */
  function confirm() {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      error.value = 'WS 未连接'
      return
    }
    const pid = projectId()
    if (!pid || !currentStep.value) {
      error.value = 'project_id 或 step 缺失'
      return
    }
    if (Object.keys(fields.value).length === 0) {
      error.value = '字段为空，请先让 Agent 提议'
      return
    }
    addUserMessage('✅ 确认这 4 个字段，写入 7 件基座')
    ws.value.send(JSON.stringify({
      type: 'onboarding_confirm',
      project_id: pid,
      step: currentStep.value,
      fields: { ...fields.value },
    }))
  }

  function close() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    connected.value = false
    currentStep.value = null
  }

  onUnmounted(() => {
    close()
  })

  return {
    // state
    ws,
    connected,
    connecting,
    currentStep,
    fields,
    messages,
    thinking,
    error,
    stepDone,
    // computed
    hasFields: computed(() => Object.keys(fields.value).length > 0),
    isStreaming: computed(() => thinking.value),
    // actions
    open,
    requestProposal,
    confirm,
    close,
    // helpers (for parent to render)
    addUserMessage,
    addAgentMessage,
  }
}