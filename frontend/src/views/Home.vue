<script setup lang="ts">
/**
 * Home 首页（v0.6 s5 对话式入口 · 琉璃宫升级版）
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import ChatBox from '@/components/ChatBox.vue'
import heroImage from '@/assets/首页-主图.png'

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

function toggleProjectCards() {
  showProjectCards.value = !showProjectCards.value
}

function goToProject(projectId: string) {
  showProjectCards.value = false
  router.push(`/reader/${projectId}/1`)
}
</script>

<template>
  <div class="home">
    <!-- 主图 LOGO 区域 -->
    <div class="hero-logo-area">
      <div class="hero-glow">
        <img :src="heroImage" alt="logo" class="hero-logo" />
      </div>
    </div>

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

    <!-- 主聊天区（管家大厅） -->
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
.home {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

/* 主图 LOGO 区域 */
.hero-logo-area {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 4px 24px 0px;
  animation: heroIn 500ms var(--ease-spring) 100ms both;
}

@keyframes heroIn {
  from { opacity: 0; transform: scale(0.95); }
  to   { opacity: 1; transform: scale(1); }
}

.hero-glow {
  padding: 6px 16px;
  border-radius: var(--radius-lg);
  background: radial-gradient(ellipse at center,
    rgba(255, 143, 177, 0.15) 0%,
    rgba(139, 92, 246, 0.08) 50%,
    transparent 100%);
  transition: background var(--dur-base) var(--ease-out);
}

.hero-glow:hover {
  background: radial-gradient(ellipse at center,
    rgba(255, 143, 177, 0.25) 0%,
    rgba(139, 92, 246, 0.12) 50%,
    transparent 100%);
}

.hero-logo {
  height: 96px;
  width: auto;
  display: block;
  border-radius: var(--radius-md);
  filter: drop-shadow(0 0 12px rgba(255, 143, 177, 0.3));
}

/* 聊天区 */
.chat-main {
  flex: 1;
  padding: 0 24px 4px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
  animation: fadeInUp 400ms var(--ease-spring) 300ms both;
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
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--glass-bg);
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--dur-fast);
  float: right;
}

.close-btn:hover {
  background: rgba(248, 113, 113, 0.2);
  color: var(--color-error);
}

/* 浮层过渡 */
.dialog-fade-enter-active {
  transition: opacity 200ms;
}
.dialog-fade-enter-active .project-panel {
  animation: dialogIn 300ms var(--ease-spring);
}
.dialog-fade-leave-active {
  transition: opacity 150ms var(--ease-in);
}
.dialog-fade-leave-active .project-panel {
  transition: transform 150ms var(--ease-in), opacity 150ms;
  transform: scale(0.96);
  opacity: 0;
}
.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}

/* reduced-motion */
@media (prefers-reduced-motion: reduce) {
  .hero-logo-area, .chat-main, .project-card {
    animation: none;
    opacity: 1;
  }
}

/* 移动端 */
@media (max-width: 375px) {
  .hero-logo {
    height: 64px;
  }
  .chat-main {
    padding: 0 16px 12px;
  }
}
</style>
