<script setup lang="ts">
/**
 * ChatBox — 通用管家对话组件（琉璃宫升级版）
 * 前端不展示 tool_call / tool_result 消息
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
    chatContainer.value.scrollTo({ top: chatContainer.value.scrollHeight, behavior: 'smooth' })
  }
})

function send() {
  const text = inputText.value.trim()
  if (!text || chat.thinking.value) return
  inputText.value = ''
  chat.send(text, props.projectId)
}

function onConfirm(action: string, confirmed: boolean) {
  chat.sendConfirm(action, confirmed)
}
</script>

<template>
  <div class="chatbox">
    <div ref="chatContainer" class="chatbox-messages">
      <div
        v-for="(msg, idx) in chat.messages.value"
        :key="idx"
        :class="['message', msg.role]"
      >
        <!-- 用户消息 -->
        <div v-if="msg.role === 'user'" class="bubble-user">
          {{ msg.content }}
        </div>

        <!-- 管家消息 -->
        <div v-else-if="msg.role === 'agent'" class="bubble-agent">
          <div v-if="msg.thinking" class="thinking">
            <span class="typing-cursor">▋</span>
            <span class="thinking-text">{{ msg.content }}</span>
          </div>
          <div v-else class="agent-content">
            <pre>{{ msg.content }}</pre>
            <!-- 项目卡片（structured_data.projects / cards） -->
            <div
              v-if="msg.structuredData && (msg.structuredData.projects || msg.structuredData.cards) && (msg.structuredData.projects || msg.structuredData.cards).length"
              class="project-cards"
            >
              <div
                v-for="p in (msg.structuredData.projects || msg.structuredData.cards)"
                :key="p.id"
                class="mini-card"
                @click="$emit('jump', `/reader/${p.id}/1`)"
              >
                <div class="card-name">《{{ p.name }}》</div>
                <div class="card-meta">
                  · {{ p.updated_at?.slice(0, 10) || '未知' }}
                </div>
              </div>
            </div>
            <!-- 跳转按钮 -->
            <button
              v-if="msg.structuredData && msg.structuredData.jump_url"
              class="jump-btn"
              @click="$emit('jump', msg.structuredData.jump_url)"
            >
              <i class="ph ph-arrow-right"></i>
              打开项目
            </button>
            <!-- 候选项目 -->
            <div
              v-if="msg.structuredData && msg.structuredData.candidates && msg.structuredData.candidates.length > 1"
              class="candidate-list"
            >
              <div class="candidate-label">选择项目：</div>
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

        <!-- tool 消息不展示（前端不对外展示 TOOL 调用信息） -->
      </div>

      <!-- "正在思考"指示器 -->
      <div v-if="chat.thinking.value" class="thinking-indicator">
        <span class="typing-cursor">▋</span>
        <span>管家正在思考...</span>
      </div>
    </div>

    <!-- 二次确认对话框 -->
    <transition name="confirm-fade">
      <div v-if="chat.requireConfirm.value" class="confirm-backdrop">
        <div class="confirm-panel">
          <div class="confirm-title">
            <i class="ph ph-warning"></i>
            需要二次确认
          </div>
          <div class="confirm-message">这是一次危险操作，请确认是否继续？</div>
          <div class="confirm-actions">
            <button class="btn-cancel" @click="onConfirm('danger', false)">取消</button>
            <button class="btn-confirm-danger" @click="onConfirm('danger', true)">确认</button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 输入框 -->
    <div class="chatbox-input">
      <textarea
        v-model="inputText"
        :placeholder="placeholder"
        :disabled="chat.thinking.value || !chat.connected.value"
        @keydown.enter.exact.prevent="send"
      ></textarea>
      <button
        class="send-btn"
        :disabled="!inputText.trim() || chat.thinking.value || !chat.connected.value"
        @click="send"
      >
        <i class="ph ph-paper-plane-tilt"></i>
        <span>发送</span>
      </button>
    </div>

    <div v-if="chat.error.value" class="error-bar">
      <i class="ph ph-warning-circle"></i>
      {{ chat.error.value }}
    </div>
  </div>
</template>

<style scoped>
.chatbox {
  display: flex;
  flex-direction: column;
  height: 600px;
  max-height: 700px;
  min-height: 300px;
  background: rgba(20, 20, 30, 0.6);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  position: relative;
}

.chatbox-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  scroll-behavior: smooth;
}

.message {
  display: flex;
  flex-direction: column;
}

/* User 气泡 */
.bubble-user {
  align-self: flex-end;
  max-width: 70%;
  padding: 10px 16px;
  background: linear-gradient(135deg, var(--color-sakura), var(--color-violet));
  color: #fff;
  border-radius: 18px 18px 4px 18px;
  font-size: var(--text-sm);
  line-height: 1.55;
  box-shadow: var(--glow-sakura);
  animation: slideInRight 300ms var(--ease-spring);
  white-space: pre-wrap;
  word-break: break-word;
}

/* Agent 气泡 */
.bubble-agent {
  align-self: flex-start;
  max-width: 85%;
  padding: 12px 16px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--color-text-primary);
  border-radius: 18px 18px 18px 4px;
  animation: slideInLeft 300ms var(--ease-spring);
}

.agent-content pre {
  white-space: pre-wrap;
  font-family: inherit;
  margin: 0;
  font-size: var(--text-sm);
}

/* 思考状态 */
.thinking {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--color-text-secondary);
  font-style: italic;
  opacity: 0.6;
}

.typing-cursor {
  display: inline-block;
  color: var(--color-sakura);
  animation: blink 1s step-end infinite;
}

.thinking-text {
  font-size: var(--text-sm);
}

/* "正在思考"指示器 */
.thinking-indicator {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
  font-style: italic;
  opacity: 0.5;
  animation: thinking-pulse 2s ease-in-out infinite;
}

/* 项目卡片 */
.project-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.mini-card {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}

.mini-card:hover {
  background: var(--glass-bg-hover);
  border-color: rgba(255, 143, 177, 0.3);
  transform: translateY(-2px);
  box-shadow: var(--glow-sakura);
}

.card-name {
  font-weight: 600;
  margin-bottom: 4px;
  font-size: var(--text-sm);
}

.card-meta {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

/* 跳转按钮 */
.jump-btn {
  margin-top: 12px;
  padding: 8px 16px;
  background: linear-gradient(135deg, var(--color-violet), var(--color-sakura));
  border: none;
  border-radius: var(--radius-sm);
  color: #fff;
  cursor: pointer;
  font-size: var(--text-sm);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all var(--dur-fast) var(--ease-out);
}

.jump-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--glow-sakura);
}

.jump-btn:active {
  transform: scale(0.96);
}

/* 候选项目 */
.candidate-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.candidate-label {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.candidate-item {
  padding: 8px 12px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: all var(--dur-fast);
}

.candidate-item:hover {
  background: var(--glass-bg-hover);
}

/* 输入区 */
.chatbox-input {
  display: flex;
  padding: 12px;
  gap: 8px;
  border-top: 1px solid var(--glass-border);
}

.chatbox-input textarea {
  flex: 1;
  height: 60px;
  resize: none;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  padding: 8px 12px;
  color: var(--color-text-primary);
  font-family: inherit;
  font-size: var(--text-sm);
  outline: none;
  transition: border-color var(--dur-base) var(--ease-spring), box-shadow var(--dur-base) var(--ease-spring);
}

.chatbox-input textarea:focus {
  border-color: var(--color-sakura);
  box-shadow: 0 0 0 3px rgba(255, 143, 177, 0.15);
}

.chatbox-input textarea:disabled {
  opacity: 0.5;
}

/* 发送按钮 */
.send-btn {
  padding: 8px 20px;
  background: linear-gradient(135deg, var(--color-violet), var(--color-sakura));
  border: none;
  border-radius: var(--radius-md);
  color: #fff;
  cursor: pointer;
  font-weight: 600;
  font-size: var(--text-sm);
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all var(--dur-fast) var(--ease-out);
}

.send-btn:hover:not(:disabled) {
  box-shadow: var(--glow-sakura);
}

.send-btn:active:not(:disabled) {
  transform: scale(0.96);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.send-btn i {
  font-size: 16px;
}

/* 确认对话框 */
.confirm-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.confirm-panel {
  background: rgba(27, 16, 53, 0.95);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  padding: 24px;
  max-width: 400px;
  width: 90%;
}

.confirm-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-lg);
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--color-warning);
}

.confirm-title i {
  font-size: 20px;
}

.confirm-message {
  margin-bottom: 20px;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.confirm-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.btn-cancel {
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  background: var(--glass-bg);
  color: var(--color-text-primary);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: background var(--dur-fast);
}

.btn-cancel:hover {
  background: var(--glass-bg-hover);
}

.btn-confirm-danger {
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, #ff5b5b, #ff8a5b);
  color: #fff;
  cursor: pointer;
  font-size: var(--text-sm);
  border: none;
  transition: all var(--dur-fast);
}

.btn-confirm-danger:hover {
  box-shadow: 0 0 12px rgba(255, 91, 91, 0.4);
}

.btn-confirm-danger:active {
  transform: scale(0.96);
}

/* 确认对话框过渡 */
.confirm-fade-enter-active .confirm-panel {
  animation: dialogIn 300ms var(--ease-spring);
}
.confirm-fade-enter-active {
  transition: opacity 200ms;
}
.confirm-fade-leave-active {
  transition: opacity 150ms var(--ease-in);
}
.confirm-fade-enter-from,
.confirm-fade-leave-to {
  opacity: 0;
}

/* 错误栏 */
.error-bar {
  background: rgba(255, 80, 80, 0.2);
  color: var(--color-error);
  padding: 8px 16px;
  font-size: var(--text-sm);
  border-top: 1px solid rgba(255, 80, 80, 0.3);
  display: flex;
  align-items: center;
  gap: 6px;
}

.error-bar i {
  font-size: 16px;
}

/* reduced-motion */
@media (prefers-reduced-motion: reduce) {
  .bubble-user, .bubble-agent, .thinking-indicator {
    animation: none;
    opacity: 1;
  }
  .typing-cursor {
    animation: none;
  }
}

/* 移动端 */
@media (max-width: 375px) {
  .bubble-user { max-width: 85%; }
  .bubble-agent { max-width: 95%; }
  .send-btn span { display: none; }
}
</style>
