<script setup lang="ts">
/**
 * Chat 管家对话页（从 Home 拆出）
 * 聊天为主入口，用户和管家 AI 对话创建/管理项目
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import ChatBox from '@/components/ChatBox.vue'

const router = useRouter()
const projectsStore = useProjectsStore()
const showProjectCards = ref(false)

onMounted(async () => {
  await projectsStore.loadList()
})

const recentProjects = computed(() =>
  projectsStore.projects.slice(0, 7)
)

function onJump(url: string) {
  router.push(url)
}

function goToProject(projectId: string) {
  showProjectCards.value = false
  router.push(`/reader/${projectId}/1`)
}
</script>

<template>
  <div class="chat-page">
    <!-- 顶部标题栏 -->
    <header class="chat-header">
      <button class="back-btn" @click="router.push({ name: 'home' })">
        <i class="ph ph-arrow-left"></i>
      </button>
      <h1 class="title">管家对话</h1>
      <button class="projects-btn" @click="showProjectCards = !showProjectCards">
        <i class="ph ph-books"></i>
        我的项目 ({{ projectsStore.projects.length }})
      </button>
    </header>

    <!-- 项目卡片浮层 -->
    <transition name="dialog-fade">
      <div v-if="showProjectCards" class="project-overlay" @click.self="showProjectCards = false">
        <div class="project-panel">
          <button class="close-btn" @click="showProjectCards = false">
            <i class="ph ph-x"></i>
          </button>
          <h2>我的小说项目</h2>
          <div v-if="recentProjects.length === 0" class="empty-state">
            <p>还没有项目。和管家说「我想写个故事」开始创建吧。</p>
          </div>
          <div v-else class="project-grid">
            <div
              v-for="(p, i) in recentProjects"
              :key="p.id"
              class="project-card"
              :style="{ animationDelay: `${i * 40}ms` }"
              @click="goToProject(p.id)"
            >
              <div class="project-name">《{{ p.name }}》</div>
              <div class="project-meta">
                <span>{{ p.chapter_count || 0 }} 章</span>
                <span v-if="p.palette">· {{ p.palette.slice(0, 16) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- 聊天区 -->
    <main class="chat-main">
      <ChatBox
        placeholder="和管家聊聊你的小说世界... 比如「我想写个赛博朋克爱情故事」或「我有哪些小说」"
        :welcome-message="`👋 你好！我是你的小说管家。\n\n说说想写什么、想改什么、想问什么——随便聊。\n\n• 「我想写个故事」→ 引导你创建项目\n• 「我有哪些小说」→ 列出你的项目\n• 「打开《xxx》」→ 进入指定项目\n• 「以后默认探索度用 standard」→ 调整全局偏好`"
        @jump="onJump"
        @require-confirm="(action) => console.log('需要确认:', action)"
      />
    </main>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px);
  overflow: hidden;
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  padding: 12px 24px;
  gap: 16px;
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--glass-border);
  animation: fadeInDown 300ms var(--ease-spring);
}

.back-btn {
  width: 36px; height: 36px;
  border-radius: 50%;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  display: flex; align-items: center; justify-content: center;
  transition: all var(--dur-fast) var(--ease-out);
}
.back-btn:hover { background: var(--glass-bg-hover); }
.back-btn:active { transform: scale(0.96); }
.back-btn i { font-size: 18px; }

.title {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  flex: 1;
  margin: 0;
  background: linear-gradient(135deg, var(--color-sakura), var(--color-violet));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.projects-btn {
  padding: 8px 16px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all var(--dur-base) var(--ease-out);
}
.projects-btn:hover {
  background: var(--glass-bg-hover);
  border-color: rgba(255, 143, 177, 0.3);
}
.projects-btn:active { transform: scale(0.96); }
.projects-btn i { font-size: 18px; }

/* 聊天区 */
.chat-main {
  flex: 1;
  padding: 16px 24px 16px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
  animation: fadeInUp 400ms var(--ease-spring) 100ms both;
}

/* 项目浮层 */
.project-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.project-panel {
  background: rgba(27, 16, 53, 0.95);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  padding: 24px;
  max-width: 800px;
  max-height: 80vh;
  overflow-y: auto;
  width: 90%;
}
.project-panel h2 {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  margin: 0 0 20px;
  color: var(--color-sakura);
}
.empty-state {
  color: var(--color-text-tertiary);
  text-align: center;
  padding: 40px;
}
.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.project-card {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  padding: 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--dur-base) var(--ease-spring);
  animation: cardIn 300ms var(--ease-spring) both;
}
.project-card:hover {
  background: var(--glass-bg-hover);
  border-color: rgba(255, 143, 177, 0.3);
  transform: translateY(-3px);
}
.project-name {
  font-weight: 600;
  font-size: var(--text-base);
  margin-bottom: var(--space-2);
}
.project-meta {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}
.close-btn {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: var(--glass-bg);
  color: var(--color-text-secondary);
  display: flex; align-items: center; justify-content: center;
  transition: all var(--dur-fast);
  float: right;
}
.close-btn:hover {
  background: rgba(248, 113, 113, 0.2);
  color: var(--color-error);
}

.dialog-fade-enter-active { transition: opacity 200ms; }
.dialog-fade-enter-active .project-panel { animation: dialogIn 300ms var(--ease-spring); }
.dialog-fade-leave-active { transition: opacity 150ms var(--ease-in); }
.dialog-fade-leave-active .project-panel { transition: transform 150ms var(--ease-in), opacity 150ms; transform: scale(0.96); opacity: 0; }
.dialog-fade-enter-from, .dialog-fade-leave-to { opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  .chat-header, .chat-main, .project-card { animation: none; opacity: 1; }
}
@media (max-width: 375px) {
  .chat-header { padding: 10px 16px; }
  .title { font-size: 16px; }
  .chat-main { padding: 12px 16px; }
}
</style>
