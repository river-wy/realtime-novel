<script setup lang="ts">
/**
 * Home 首页（v0.6 s5 对话式入口）
 *
 * v0.5 → v0.6 变化：
 * - v0.5: 静态 hero + 项目卡片列表 + 「新启动」按钮
 * - v0.6: 大聊天框为主（管家大厅模式），项目卡片作为次要入口
 *
 * 对应 spec.md §2.1 目标 2：「首页 = 管家大厅通用 AI 入口」
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import ChatBox from '@/components/ChatBox.vue'
import heroImage from '@/assets/首页-主图.png'

const router = useRouter()
const projectsStore = useProjectsStore()
const showProjectCards = ref(false)  // 项目卡片浮层（点击「我的项目」时显示）

onMounted(async () => {
  await projectsStore.loadList()
})

const recentProjects = computed(() =>
  projectsStore.projects.slice(0, 7)
)

function onJump(url: string) {
  // ChatBox emit jump（structured_data.jump_url 触发）
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
    <!-- 顶部导航 -->
    <header class="home-header">
      <img :src="heroImage" alt="logo" class="logo" />
      <h1 class="title">小说·世界</h1>
      <button class="projects-btn" @click="toggleProjectCards">
        我的项目 ({{ projectsStore.projects.length }})
      </button>
    </header>

    <!-- 项目卡片浮层 -->
    <div v-if="showProjectCards" class="project-overlay" @click.self="showProjectCards = false">
      <div class="project-panel">
        <h2>我的小说项目</h2>
        <div v-if="recentProjects.length === 0" class="empty-state">
          <p>还没有项目。和管家说「我想写个故事」开始创建吧。</p>
        </div>
        <div v-else class="project-grid">
          <div
            v-for="p in recentProjects"
            :key="p.id"
            class="project-card"
            @click="goToProject(p.id)"
          >
            <div class="project-name">《{{ p.name }}》</div>
            <div class="project-meta">
              <span>{{ p.chapter_count || 0 }} 章</span>
              <span v-if="p.palette">· {{ p.palette.slice(0, 16) }}</span>
            </div>
          </div>
        </div>
        <button class="close-btn" @click="showProjectCards = false">关闭</button>
      </div>
    </div>

    <!-- 主聊天区（管家大厅） -->
    <main class="chat-main">
      <ChatBox
        placeholder="和管家聊聊你的小说世界... 比如「我想写个赛博朋克爱情故事」或「我有哪些小说」"
        :welcome-message="`👋 你好！我是你的小说管家。\n\n说说想写什么、想改什么、想问什么——随便聊。\n\n• 「我想写个故事」→ 引导你创建项目\n• 「我有哪些小说」→ 列出你的项目\n• 「打开《xxx》」→ 进入指定项目\n• 「以后默认探索度用 standard」→ 调整全局偏好`"
        @jump="onJump"
        @require-confirm="(action) => console.log('需要确认:', action)"
      />
    </main>

    <!-- 底部兜底入口（按钮式 Onboarding，按 18:02 拍板保留） -->
    <footer class="home-footer">
      <a @click.prevent="router.push('/onboarding')">老版本表单入口 →</a>
    </footer>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
  color: white;
}

.home-header {
  display: flex;
  align-items: center;
  padding: 16px 24px;
  gap: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.logo {
  width: 40px;
  height: 40px;
  border-radius: 8px;
}

.title {
  font-size: 22px;
  font-weight: 600;
  margin: 0;
  flex: 1;
  background: linear-gradient(135deg, #f093fb, #f5576c);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.projects-btn {
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  color: white;
  cursor: pointer;
  font-size: 14px;
}

.projects-btn:hover {
  background: rgba(255, 255, 255, 0.15);
}

.project-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}

.project-panel {
  background: rgba(20, 20, 35, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 16px;
  padding: 24px;
  max-width: 800px;
  max-height: 80vh;
  overflow-y: auto;
  width: 90%;
}

.project-panel h2 {
  margin: 0 0 20px;
  font-size: 20px;
}

.empty-state {
  color: rgba(255, 255, 255, 0.6);
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
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.project-card:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(140, 100, 255, 0.5);
  transform: translateY(-2px);
}

.project-name {
  font-weight: 600;
  font-size: 16px;
  margin-bottom: 8px;
}

.project-meta {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
}

.close-btn {
  padding: 8px 20px;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  border-radius: 8px;
  color: white;
  cursor: pointer;
}

.chat-main {
  flex: 1;
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
}

.home-footer {
  text-align: center;
  padding: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.home-footer a {
  color: rgba(255, 255, 255, 0.4);
  text-decoration: none;
  font-size: 12px;
  cursor: pointer;
}

.home-footer a:hover {
  color: rgba(255, 255, 255, 0.7);
}
</style>