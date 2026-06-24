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
import {computed, onUnmounted, ref} from 'vue'

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

  /** Agent 提议的大纲 (4 字段) */
  const fields = ref<Record<string, string>>({})

  /** 对话历史（Agent 引导语 + 用户修改意见） */
  const messages = ref<OnboardingChatMessage[]>([])

  /** Agent 是否在思考 */
  const thinking = ref(false)

  /** 最近一次错误 */
  const error = ref<string | null>(null)

  /** Step 是否已完成（onboarding_step_done 收到） */
  const stepDone = ref(false)

  /** confirm 是否正在发送中（防双击） */
  const confirming = ref(false)

  /** Step 4 完成后 LLM 自动生成的项目名（通过 project_name_updated 事件接收） */
  const generatedProjectName = ref<string | null>(null)

  /** Step 4 完成后生成的封面图 URL（通过 cover_image_updated 事件接收） */
  const generatedCoverImageUrl = ref<string | null>(null)

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

  /**
   * 打开 WS 连接并进入指定 step
   * @param step 3 or 4
   * @param initialFields 续接时传入的已落库字段（传入时直接回填，跳过自动 proposal）
   */
  function open(step: OnboardingStepNum, initialFields?: Record<string, string>) {
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
    // 续接：预填已有字段（不触发 proposal，让用户决定是否重新生成）
    fields.value = initialFields ? { ...initialFields } : {}
    messages.value = []
    stepDone.value = false

    // 是否为续接（有已有数据）
    const hasInitialFields = initialFields && Object.keys(initialFields).length > 0

    const socket = new WebSocket(WS_BASE)
    socket.onopen = () => {
      // v0.8.3 修复: 只在还是同一个 ws 时才设 connected + 加开场白 (避免旧 ws onopen 误开新 ws 状态)
      if (ws.value === socket) {
        connected.value = true
        connecting.value = false
        if (hasInitialFields) {
          // 续接模式：显示上次数据已恢复，不自动触发 proposal
          addAgentMessage(
            step === 3
              ? '👋 欢迎回来！我已为你恢复了上次的故事大纲。\n\n你可以直接「确认大纲 → 写 7 件」，或告诉我你想调整的方向，也可以点「让 Agent 重新提议」换一套方案。'
              : '👋 欢迎回来！我已为你恢复了上次的大纲细化内容。\n\n你可以直接「确认大纲 → 写 7 件」，或告诉我你想调整的方向，也可以点「让 Agent 重新提议」换一套方案。',
          )
          // 续接不自动触发 proposal，让用户主动操作
        } else {
          // 全新模式：自动触发第一次提议
          addAgentMessage(
            step === 3
              ? '👋 你好！我是你的小说创作引导师。\n\n我已经看过你在 Step 1 选择的题材/风格/基调，也看到了 Step 2 的视觉色调偏好。正在为你生成故事大纲...'
              : '👋 现在我们进入 Step 4 大纲细化。\n\nStep 3 的故事大纲已经写入 7 件基座。正在为你进一步细化大纲...',
          )
          // silent=true: 开场白已含「正在生成...」，跳过多余的 inline 提示
          requestProposal('', true)
        }
      }
    }
    socket.onmessage = (event) => {
      // v0.8.3 修复: 只处理当前 ws 的消息 (避免旧 ws 消息污染新 ws 状态)
      if (ws.value !== socket) return
      try {
        const msg = JSON.parse(event.data)
        handleEvent(msg)
      } catch (e) {
        console.error('[OnboardingChat] WS parse error', e)
      }
    }
    socket.onclose = () => {
      // v0.8.3 修复: 只在还是同一个 ws 时才清空状态 (race condition 防护)
      // 旧 ws 异步 close 时不应清掉新 ws 状态
      if (ws.value === socket) {
        connected.value = false
        ws.value = null
      }
    }
    socket.onerror = () => {
      if (ws.value === socket) {
        error.value = 'WebSocket 连接错误'
        connecting.value = false
      }
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
        '✅ 已为你生成故事大纲。点击右下「确认大纲」按钮，或者继续在输入框告诉我你想调整的方向。',
      )
    } else if (t === 'onboarding_confirmed') {
      thinking.value = false
      confirming.value = false
      addAgentMessage(
        `✅ Step ${msg.step} 字段已写入 7 件基座（${msg.artifacts_written?.join(', ') || ''}）`,
      )
    } else if (t === 'onboarding_step_done') {
      thinking.value = false
      stepDone.value = true
      addAgentMessage(`🎉 Step ${msg.step} 完成，准备进入 Step ${msg.next_step}。`)
    } else if (t === 'project_name_updated') {
      // Step 4 完成后 LLM 自动生成的世界名称
      if (msg.name) {
        generatedProjectName.value = msg.name
      }
    } else if (t === 'cover_image_updated') {
      // Step 4 完成后生成的封面图 URL
      if (msg.cover_image_url) {
        generatedCoverImageUrl.value = msg.cover_image_url
      }
    } else if (t === 'error') {
      thinking.value = false
      confirming.value = false
      error.value = msg.message || '未知错误'
      addAgentMessage(`❌ 错误：${msg.message || '未知错误'}`)
    } else {
      // 其它事件（conversation_started 等）忽略
      console.debug('[OnboardingChat] 忽略事件:', t, msg)
    }
  }

  /**
   * 让 Agent 提议大纲 (4 字段)
   * @param userMessage 首次自动触发传 ''，后续用户修改意见传文字
   * @param silent 为 true 时跳过「🤔 正在为你生成...」提示（自动触发时开场白已经说了）
   */
  function requestProposal(userMessage = '', silent = false) {
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
    } else if (!silent) {
      addAgentMessage('🤔 正在为你生成故事大纲...')
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
   * 用户确认大纲 → 写 7 件
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
    // 防双击：发送中时直接忽略
    if (confirming.value) return
    confirming.value = true
    addUserMessage('✅ 确认这个大纲，写入 7 件基座')
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
    confirming,
    generatedProjectName,  // Step 4 完成后 LLM 生成的世界名称
    generatedCoverImageUrl,  // Step 4 完成后生成的封面图 URL
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