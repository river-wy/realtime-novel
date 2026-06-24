/**
 * useStewardChat — 通用管家对话 composable（v0.6 s5）
 *
 * 与 useOnboardingChat 的区别：
 * - 不绑 step（通用对话）
 * - 支持所有 intent（CREATE_PROJECT / GENERATE / INTERVENE / LIST_PROJECTS / ...）
 * - 处理 agent_message + structured_data + confirm_required 事件
 * - 暴露 jump_url 让前端能跳转
 */
import {computed, onUnmounted, ref} from 'vue'

const WS_BASE = `ws://${window.location.host}/api/chat`

export interface StewardMessage {
  role: 'agent' | 'user' | 'system' | 'tool'
  content: string
  /** tool 调用详情（role=tool 时） */
  toolName?: string
  toolArgs?: Record<string, any>
  toolResult?: any
  /** thinking 流（LLM 思考中） */
  thinking?: boolean
  timestamp: number
  /** 后端 structured_data（项目列表/跳转 URL/确认卡片等） */
  structuredData?: Record<string, any>
}

export function useStewardChat() {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const connecting = ref(false)
  const messages = ref<StewardMessage[]>([])
  const thinking = ref(false)
  const error = ref<string | null>(null)
  const intent = ref<string | null>(null)
  const structuredData = ref<Record<string, any> | null>(null)
  const requireConfirm = ref(false)

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

  function addToolMessage(toolName: string, args: any, result: any) {
    messages.value.push({
      role: 'tool',
      content: `调用 ${toolName}`,
      toolName,
      toolArgs: args,
      toolResult: result,
      timestamp: Date.now(),
    })
  }

  function connect() {
    if (ws.value) return  // 已连接
    connecting.value = true
    error.value = null

    const socket = new WebSocket(WS_BASE)
    socket.onopen = () => {
      if (ws.value === socket) {
        connected.value = true
        connecting.value = false
      }
    }
    socket.onmessage = (event) => {
      if (ws.value !== socket) return
      try {
        const msg = JSON.parse(event.data)
        handleEvent(msg)
      } catch (e) {
        console.error('[StewardChat] WS parse error', e)
      }
    }
    socket.onclose = () => {
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
    } else if (t === 'tool_calling') {
      // 工具调用中（前端可展示「正在调用 search_memory...」）
      addAgentMessage(`🔧 调用工具：${msg.tool}（参数：${JSON.stringify(msg.args || {}).slice(0, 80)}...）`)
    } else if (t === 'tool_result') {
      // 工具结果（前端可折叠/隐藏）
      addToolMessage(msg.tool, msg.args, msg.result)
    } else if (t === 'agent_message') {
      // 最终回复
      thinking.value = false
      intent.value = msg.intent || null
      structuredData.value = msg.structured_data || null
      // 替换最后一条 thinking 消息为最终消息
      let lastThinkingIdx = -1
      for (let i = messages.value.length - 1; i >= 0; i--) {
        const m = messages.value[i]
        if (m && m.role === 'agent' && m.thinking) {
          lastThinkingIdx = i
          break
        }
      }
      if (lastThinkingIdx >= 0) {
        messages.value[lastThinkingIdx] = {
          role: 'agent',
          content: msg.content || '',
          timestamp: Date.now(),
          structuredData: msg.structured_data,
        }
      } else {
        addAgentMessage(msg.content || '')
      }
      // 触发前端可监听的回调
      onAgentMessage?.(msg)
    } else if (t === 'confirm_required') {
      requireConfirm.value = true
      onConfirmRequired?.(msg)
    } else if (t === 'error') {
      thinking.value = false
      error.value = msg.message || '未知错误'
      addAgentMessage(`❌ 错误：${msg.message || '未知错误'}`)
    } else if (t === 'interrupted') {
      thinking.value = false
      addAgentMessage(`⏸️ ${msg.message || '已中断'}`)
    } else if (t === 'pong') {
      // 心跳响应，忽略
    } else {
      console.debug('[StewardChat] 未知事件:', t, msg)
    }
  }

  function send(content: string, projectId?: string | null) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      error.value = 'WebSocket 未连接'
      return
    }
    addUserMessage(content)
    ws.value.send(JSON.stringify({
      type: 'user_message',
      content,
      project_id: projectId || undefined,
    }))
  }

  function sendConfirm(action: string, confirmed: boolean) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) return
    ws.value.send(JSON.stringify({
      type: 'confirm',
      action,
      confirmed,
    }))
    if (confirmed) {
      requireConfirm.value = false
    }
  }

  function close() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    connected.value = false
  }

  // 可选回调（前端可监听）
  let onAgentMessage: ((msg: any) => void) | null = null
  let onConfirmRequired: ((msg: any) => void) | null = null
  function setOnAgentMessage(fn: ((msg: any) => void) | null) { onAgentMessage = fn }
  function setOnConfirmRequired(fn: ((msg: any) => void) | null) { onConfirmRequired = fn }

  onUnmounted(() => {
    close()
  })

  return {
    // 状态
    ws,
    connected,
    connecting,
    messages,
    thinking,
    error,
    intent,
    structuredData,
    requireConfirm,
    // 方法
    connect,
    send,
    sendConfirm,
    close,
    setOnAgentMessage,
    setOnConfirmRequired,
  }
}