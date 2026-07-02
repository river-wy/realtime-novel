/**
 * Conversation store（一对一 active conv + 新建对话）
 *
 * 一个 user 只有一个 active conv
 * "新建对话" = 让旧 active 失效 + 调 LLM 准备新 conv
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const WS_BASE = `ws://${window.location.host}/api/chat`

export const useConversationStore = defineStore('conversation', () => {
  const activeConvId = ref<string | null>(null)
  const status = ref<'active' | 'invalidated' | 'archived' | 'none'>('none')
  const ws = ref<WebSocket | null>(null)
  const messages = ref<Array<{ role: 'user' | 'assistant' | 'tool'; content: string; tool_calls?: any }>>([])
  const connected = ref(false)
  const streaming = ref(false)

  function connect() {
    if (ws.value) return
    const socket = new WebSocket(WS_BASE)
    socket.onopen = () => {
      connected.value = true
    }
    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'conversation_started') {
          activeConvId.value = msg.conversation_id
          status.value = 'active'
        } else if (msg.type === 'conversation_invalidated') {
          status.value = 'invalidated'
        } else if (msg.type === 'assistant_chunk') {
          streaming.value = true
          // 追加到最后一条 assistant 消息
          const last = messages.value[messages.value.length - 1]
          if (last && last.role === 'assistant') {
            last.content += msg.delta || ''
          } else {
            messages.value.push({ role: 'assistant', content: msg.delta || '' })
          }
        } else if (msg.type === 'assistant_done') {
          streaming.value = false
        } else if (msg.type === 'tool_call') {
          messages.value.push({ role: 'tool', content: '', tool_calls: msg.tool_call })
        } else if (msg.type === 'error') {
          error.value = msg.message
          streaming.value = false
        }
      } catch (e) {
        console.error('WS parse error', e)
      }
    }
    socket.onclose = () => {
      connected.value = false
      ws.value = null
    }
    socket.onerror = () => {
      error.value = 'WebSocket 连接错误'
    }
    ws.value = socket
  }

  function sendUserMessage(content: string, projectId?: string) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      error.value = 'WS 未连接'
      return
    }
    messages.value.push({ role: 'user', content })
    ws.value.send(JSON.stringify({
      type: 'user_message',
      content,
      project_id: projectId,
      conversation_id: activeConvId.value  // 后端会忽略/覆盖
    }))
  }

  /** 新建对话：关闭 WS → 重连（后端会创建新 conv） */
  function newConversation() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    activeConvId.value = null
    status.value = 'none'
    messages.value = []
    error.value = null
    connect()  // 重连
  }

  function disconnect() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    connected.value = false
  }

  const error = ref<string | null>(null)
  const isStreaming = computed(() => streaming.value)
  const hasMessages = computed(() => messages.value.length > 0)

  return { activeConvId, status, ws, messages, connected, isStreaming, hasMessages, error, connect, sendUserMessage, newConversation, disconnect }
})
