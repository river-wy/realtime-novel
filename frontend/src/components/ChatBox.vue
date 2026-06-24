<script setup lang="ts">
/**
 * ChatBox — 通用管家对话组件（v0.6 s5）
 *
 * 用于首页（Home.vue）和阅读页（Reader.vue）的右栏
 * props:
 *   - placeholder: 输入框 placeholder
 *   - projectId: 可选，关联到具体项目
 *   - initialMessages: 可选，预填消息
 * events:
 *   - jump: 跳转 URL（structured_data.jump_url 触发）
 *   - require-confirm: 需要二次确认（confirm_required 事件触发）
 */
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useStewardChat } from '@/composables/useStewardChat'

const props = withDefaults(defineProps<{
  placeholder?: string
  projectId?: string | null
  welcomeMessage?: string
}>(), {
  placeholder: '和管家聊聊你的小说...',
  projectId: null,
  welcomeMessage: '你好！我是你的小说管家。\n\n说说想写什么、想改什么、想问什么——随便聊。',
})

const emit = defineEmits<{
  jump: [url: string]
  'require-confirm': [action: string, details: any]
}>()

const chat = useStewardChat()
const inputText = ref('')
const chatContainer = ref<HTMLElement | null>(null)
const expandedTools = ref<Set<number>>(new Set())

// 监听 agent_message 触发 jump
chat.setOnAgentMessage((msg) => {
  const sd = msg.structured_data || {}
  if (sd.jump_url) {
    emit('jump', sd.jump_url)
  }
})

// 监听 confirm_required
chat.setOnConfirmRequired((msg) => {
  emit('require-confirm', msg.action, msg.details)
})

onMounted(() => {
  chat.connect()
  if (props.welcomeMessage && chat.messages.value.length === 0) {
    chat.messages.value.push({
      role: 'agent',
      content: props.welcomeMessage,
      timestamp: Date.now(),
    })
  }
})

// 自动滚动到底部
watch(() => chat.messages.value.length, async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
})

function send() {
  const text = inputText.value.trim()
  if (!text || chat.thinking.value) return
  inputText.value = ''
  chat.send(text, props.projectId)
}

function toggleTool(idx: number) {
  if (expandedTools.value.has(idx)) {
    expandedTools.value.delete(idx)
  } else {
    expandedTools.value.add(idx)
  }
}

function onConfirm(action: string, confirmed: boolean) {
  chat.sendConfirm(action, confirmed)
}
</script>

<template>
  <div class="chat-box">
    <div ref="chatContainer" class="chat-container">
      <div
        v-for="(msg, idx) in chat.messages.value"
        :key="idx"
        :class="['message', msg.role]"
      >
        <!-- 用户消息 -->
        <div v-if="msg.role === 'user'" class="user-bubble">
          {{ msg.content }}
        </div>

        <!-- 管家消息 -->
        <div v-else-if="msg.role === 'agent'" class="agent-bubble">
          <div v-if="msg.thinking" class="thinking">
            <span class="dot-flashing"></span> {{ msg.content }}
          </div>
          <div v-else class="agent-content">
            <pre>{{ msg.content }}</pre>
            <!-- 项目卡片（structured_data.projects） -->
            <div v-if="msg.structuredData && msg.structuredData.projects && msg.structuredData.projects.length" class="project-cards">
              <div
                v-for="p in msg.structuredData.projects"
                :key="p.id"
                class="project-card"
                @click="$emit('jump', `/reader/${p.id}/1`)"
              >
                <div class="card-name">《{{ p.name }}》</div>
                <div class="card-meta">
                  {{ p.palette || '未设置主题色' }}
                  · {{ p.updated_at?.slice(0, 10) || '未知' }}
                </div>
              </div>
            </div>
            <!-- 跳转按钮（structured_data.jump_url） -->
            <button
              v-if="msg.structuredData && msg.structuredData.jump_url"
              class="jump-btn"
              @click="$emit('jump', msg.structuredData.jump_url)"
            >
              打开项目 →
            </button>
            <!-- 候选项目（OPEN_PROJECT 多匹配时） -->
            <div v-if="msg.structuredData && msg.structuredData.candidates && msg.structuredData.candidates.length > 1" class="candidates">
              <div class="candidates-label">选择项目：</div>
              <div
                v-for="c in msg.structuredData.candidates"
                :key="c.id"
                class="candidate-item"
                @click="$emit('jump', `/reader/${c.id}/1`)"
              >
                《{{ c.name }}》
              </div>
            </div>
          </div>
        </div>

        <!-- Tool 消息（可折叠） -->
        <div v-else-if="msg.role === 'tool'" class="tool-bubble">
          <div class="tool-header" @click="toggleTool(idx)">
            🔧 {{ msg.toolName }}
            <span class="tool-toggle">{{ expandedTools.has(idx) ? '▾' : '▸' }}</span>
          </div>
          <div v-if="expandedTools.has(idx)" class="tool-detail">
            <div class="tool-args">
              <strong>参数:</strong>
              <pre>{{ JSON.stringify(msg.toolArgs, null, 2) }}</pre>
            </div>
            <div class="tool-result">
              <strong>结果:</strong>
              <pre>{{ JSON.stringify(msg.toolResult, null, 2).slice(0, 500) }}</pre>
            </div>
          </div>
        </div>
      </div>

      <div v-if="chat.thinking.value" class="thinking-indicator">
        <span class="dot-flashing"></span> 管家正在思考...
      </div>
    </div>

    <!-- 二次确认对话框 -->
    <div v-if="chat.requireConfirm.value" class="confirm-overlay">
      <div class="confirm-dialog">
        <div class="confirm-title">⚠️ 需要二次确认</div>
        <div class="confirm-message">这是一次危险操作，请确认是否继续？</div>
        <div class="confirm-actions">
          <button class="btn-cancel" @click="onConfirm('danger', false)">取消</button>
          <button class="btn-confirm" @click="onConfirm('danger', true)">确认</button>
        </div>
      </div>
    </div>

    <!-- 输入框 -->
    <div class="chat-input">
      <textarea
        v-model="inputText"
        :placeholder="placeholder"
        :disabled="chat.thinking.value || !chat.connected.value"
        @keydown.enter.exact.prevent="send"
      />
      <button
        class="send-btn"
        :disabled="!inputText.trim() || chat.thinking.value || !chat.connected.value"
        @click="send"
      >
        发送
      </button>
    </div>

    <div v-if="chat.error.value" class="error-bar">
      ❌ {{ chat.error.value }}
    </div>
  </div>
</template>

<style scoped>
.chat-box {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: rgba(20, 20, 30, 0.6);
  border-radius: 12px;
  overflow: hidden;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message {
  display: flex;
  flex-direction: column;
}

.user-bubble {
  align-self: flex-end;
  background: linear-gradient(135deg, #5b6cff, #8a5bff);
  color: white;
  padding: 10px 16px;
  border-radius: 18px 18px 4px 18px;
  max-width: 70%;
  word-wrap: break-word;
}

.agent-bubble {
  align-self: flex-start;
  background: rgba(255, 255, 255, 0.08);
  padding: 12px 16px;
  border-radius: 18px 18px 18px 4px;
  max-width: 85%;
  word-wrap: break-word;
}

.agent-content pre {
  white-space: pre-wrap;
  font-family: inherit;
  margin: 0;
}

.thinking {
  color: rgba(255, 255, 255, 0.6);
  font-style: italic;
}

.project-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.project-card {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}
.project-card:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(140, 100, 255, 0.4);
}

.card-name {
  font-weight: 600;
  margin-bottom: 4px;
}

.card-meta {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
}

.jump-btn {
  margin-top: 12px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #5b6cff, #8a5bff);
  border: none;
  border-radius: 8px;
  color: white;
  cursor: pointer;
}

.candidates {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.candidates-label {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
}

.candidate-item {
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 6px;
  cursor: pointer;
}
.candidate-item:hover {
  background: rgba(255, 255, 255, 0.12);
}

.tool-bubble {
  align-self: stretch;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  font-family: monospace;
}

.tool-header {
  cursor: pointer;
  user-select: none;
}

.tool-detail {
  margin-top: 8px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.7);
}

.tool-detail pre {
  white-space: pre-wrap;
  margin: 4px 0;
  background: rgba(0, 0, 0, 0.3);
  padding: 6px;
  border-radius: 4px;
}

.thinking-indicator {
  align-self: flex-start;
  color: rgba(255, 255, 255, 0.5);
  font-style: italic;
}

.dot-flashing {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.6);
  animation: dot-flashing 1.4s infinite linear;
}
@keyframes dot-flashing {
  0%, 60%, 100% { opacity: 0.2; }
  30% { opacity: 1; }
}

.confirm-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.confirm-dialog {
  background: rgba(30, 30, 45, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  padding: 24px;
  max-width: 400px;
}

.confirm-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 12px;
}

.confirm-message {
  margin-bottom: 20px;
  color: rgba(255, 255, 255, 0.8);
}

.confirm-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.btn-cancel, .btn-confirm {
  padding: 8px 16px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
}

.btn-cancel {
  background: rgba(255, 255, 255, 0.1);
  color: white;
}

.btn-confirm {
  background: linear-gradient(135deg, #ff5b5b, #ff8a5b);
  color: white;
}

.chat-input {
  display: flex;
  padding: 12px;
  gap: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.chat-input textarea {
  flex: 1;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 8px 12px;
  color: white;
  resize: none;
  height: 60px;
  font-family: inherit;
}

.send-btn {
  padding: 8px 20px;
  background: linear-gradient(135deg, #5b6cff, #8a5bff);
  border: none;
  border-radius: 8px;
  color: white;
  cursor: pointer;
  font-weight: 600;
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.error-bar {
  background: rgba(255, 80, 80, 0.2);
  color: #ffaaaa;
  padding: 8px 16px;
  font-size: 13px;
  border-top: 1px solid rgba(255, 80, 80, 0.3);
}
</style>