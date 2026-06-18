<script setup lang="ts">
/**
 * Home 首页（v0.5 接入后端 API）
 *
 * 首屏 hero + 项目列表 + "新启动" 入口
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import heroImage from '@/assets/首页-主图.png'

const router = useRouter()
const projectsStore = useProjectsStore()

onMounted(async () => {
  await projectsStore.loadList()
})

function goToProject(id: string) {
  router.push({ name: 'world', params: { projectId: id } })
}

function startNewProject() {
  router.push({ name: 'onboarding' })
}
</script>

<template>
  <div class="home">
    <!-- Hero -->
    <section class="hero fade-in">
      <div class="hero-bg">
        <div class="star"></div>
        <div class="star"></div>
        <div class="star"></div>
        <div class="star"></div>
        <div class="star"></div>
      </div>
      <img :src="heroImage" alt="realtime-novel 主图" class="hero-image" />
      <h1 class="hero-title">realtime-novel</h1>
      <p class="hero-subtitle">实时生成 · 可干预 · 可回档</p>
      <p class="hero-desc">基于 LLM 的小说创作平台。世界树 + 主线 + 人物 + 种子表，让 AI 写你心中的故事。</p>
      <div class="hero-actions">
        <button class="btn btn-primary" @click="startNewProject">✨ 新启动一个世界</button>
        <button v-if="projectsStore.projects.length > 0" class="btn btn-secondary" @click="goToProject(projectsStore.projects[0].id)">
          打开最近项目
        </button>
      </div>
    </section>

    <!-- 项目列表 -->
    <section class="projects-section">
      <h2 class="section-title">我的世界</h2>
      <div v-if="projectsStore.loading" class="loading">加载中...</div>
      <div v-else-if="projectsStore.projects.length === 0" class="empty">
        <p>还没有世界</p>
        <button class="btn btn-primary" @click="startNewProject">启动第一个世界</button>
      </div>
      <div v-else class="project-grid">
        <article
          v-for="p in projectsStore.projects"
          :key="p.id"
          class="project-card"
          @click="goToProject(p.id)"
        >
          <div class="card-bg" :style="{ background: `linear-gradient(135deg, var(--color-night-2), var(--color-night-3))` }"></div>
          <div class="card-content">
            <h3 class="card-title">{{ p.name }}</h3>
            <p class="card-meta">
              <span class="palette">{{ p.palette }}</span>
              <span class="chapter-count">{{ p.chapter_count }} 章</span>
            </p>
          </div>
        </article>
      </div>
    </section>

    <!-- 特性 -->
    <section class="features">
      <h2 class="section-title">三大特性</h2>
      <div class="feature-grid">
        <div class="feature">
          <div class="feature-icon">⚡</div>
          <h3>实时生成</h3>
          <p>基于 deepseek-v4-pro，60 秒生成一章</p>
        </div>
        <div class="feature">
          <div class="feature-icon">🎭</div>
          <h3>可干预</h3>
          <p>导演 / 演员双模式干预剧情</p>
        </div>
        <div class="feature">
          <div class="feature-icon">⏪</div>
          <h3>可回档</h3>
          <p>任意章节回档，章节 + 基座同步</p>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home {
  padding: var(--space-5) 0;
}

/* Hero */
.hero {
  position: relative;
  text-align: center;
  padding: var(--space-8) var(--space-4);
  background: linear-gradient(180deg, var(--color-night-2) 0%, transparent 100%);
  border-radius: var(--radius-lg);
  overflow: hidden;
  margin-bottom: var(--space-7);
}

.hero-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.star {
  position: absolute;
  width: 4px;
  height: 4px;
  background: var(--color-accent-2);
  border-radius: 50%;
  animation: sparkle 3s ease-in-out infinite;
}
.star:nth-child(1) { top: 20%; left: 15%; animation-delay: 0s; }
.star:nth-child(2) { top: 35%; right: 20%; animation-delay: 0.5s; }
.star:nth-child(3) { top: 60%; left: 25%; animation-delay: 1s; }
.star:nth-child(4) { top: 75%; right: 30%; animation-delay: 1.5s; }
.star:nth-child(5) { top: 45%; left: 50%; animation-delay: 2s; }

.hero-image {
  display: block;
  max-width: 480px;
  width: 100%;
  height: auto;
  margin: 0 auto var(--space-5);
  position: relative;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.hero-title {
  font-size: var(--text-4xl);
  background: linear-gradient(135deg, var(--color-accent-1), var(--color-accent-2));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: var(--space-3);
  position: relative;
}

.hero-subtitle {
  font-size: var(--text-2xl);
  color: var(--color-accent-1);
  margin-bottom: var(--space-3);
  position: relative;
}

.hero-desc {
  font-size: var(--text-base);
  color: var(--color-text-dim);
  max-width: 600px;
  margin: 0 auto var(--space-6);
  position: relative;
}

.hero-actions {
  display: flex;
  gap: var(--space-4);
  justify-content: center;
  position: relative;
}

.btn {
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-weight: 500;
  transition: all var(--motion-fast) var(--ease-out);
}

.btn-primary {
  background: linear-gradient(135deg, var(--color-accent-1), var(--color-accent-3));
  color: white;
  box-shadow: var(--shadow-glow);
}
.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 32px rgba(255, 143, 177, 0.5);
}

.btn-secondary {
  background: transparent;
  border: 1px solid var(--color-accent-3);
  color: var(--color-accent-3);
}
.btn-secondary:hover {
  background: rgba(139, 92, 246, 0.1);
}

/* Sections */
.section-title {
  font-size: var(--text-2xl);
  margin-bottom: var(--space-5);
  color: var(--color-accent-1);
}

.projects-section,
.features {
  margin-bottom: var(--space-7);
}

.loading,
.empty {
  text-align: center;
  padding: var(--space-6);
  color: var(--color-text-dim);
}

.empty .btn {
  margin-top: var(--space-4);
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}

.project-card {
  position: relative;
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  transition: transform var(--motion-base) var(--ease-out);
  min-height: 160px;
}

.project-card:hover {
  transform: translateY(-4px);
}

.card-bg {
  position: absolute;
  inset: 0;
  opacity: 0.7;
}

.card-content {
  position: relative;
  padding: var(--space-5);
}

.card-title {
  font-size: var(--text-xl);
  margin-bottom: var(--space-3);
  color: var(--color-text);
}

.card-meta {
  display: flex;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-dim);
}

.palette {
  background: rgba(139, 92, 246, 0.2);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

.chapter-count {
  color: var(--color-accent-2);
}

/* Features */
.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-4);
}

.feature {
  text-align: center;
  padding: var(--space-5);
  background: var(--color-night-2);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-night-3);
  transition: all var(--motion-base) var(--ease-out);
}

.feature:hover {
  border-color: var(--color-accent-1);
  transform: translateY(-2px);
}

.feature-icon {
  font-size: 40px;
  margin-bottom: var(--space-3);
}

.feature h3 {
  font-size: var(--text-lg);
  margin-bottom: var(--space-2);
  color: var(--color-accent-1);
}

.feature p {
  font-size: var(--text-sm);
  color: var(--color-text-dim);
  margin: 0;
}
</style>
