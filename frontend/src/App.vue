<script setup lang="ts">
import { RouterView, RouterLink, useRoute } from 'vue-router'
import { ref, computed } from 'vue'
import logoImage from '@/assets/logo文字.png'

const route = useRoute()
const isHome = computed(() => route.name === 'home')

const petals = ref(Array.from({ length: 10 }, (_, i) => ({
  id: i,
  left: `${5 + i * 9}%`,
  duration: `${16 + (i % 5) * 2}s`,
  delay: `${(i * 1.5) % 12}s`,
  scale: `${0.6 + (i % 6) * 0.1}`,
  opacity: `${0.3 + (i % 4) * 0.08}`,
})))
</script>

<template>
  <!-- 樱花飘落粒子 -->
  <div class="petal-container">
    <div
      v-for="p in petals"
      :key="p.id"
      class="petal"
      :style="{
        left: p.left,
        animationDuration: p.duration,
        animationDelay: p.delay,
        transform: `scale(${p.scale})`,
        opacity: p.opacity,
      }"
    ></div>
  </div>

  <div class="app-root">
    <!-- 导航栏：仅非 home 页显示 -->
    <nav v-if="!isHome" class="top-nav nav-glass">
      <div class="nav-inner">
        <RouterLink to="/" class="brand">
          <div class="brand-glow">
            <img :src="logoImage" alt="realtime-novel" class="brand-logo" />
          </div>
        </RouterLink>
        <div class="nav-links">
          <RouterLink to="/" class="nav-link" active-class="active">
            <i class="ph ph-sparkle"></i>
            <span>首页</span>
          </RouterLink>
          <RouterLink to="/chat" class="nav-link" active-class="active">
            <i class="ph ph-chats-circle"></i>
            <span>对话</span>
          </RouterLink>
          <RouterLink to="/worlds" class="nav-link" active-class="active">
            <i class="ph ph-globe"></i>
            <span>我的世界</span>
          </RouterLink>
        </div>
      </div>
    </nav>

    <main class="app-main">
      <RouterView v-slot="{ Component, route: r }">
        <transition name="page-slide" mode="out-in">
          <component :is="Component" :key="r.fullPath" :class="{ 'full-page': r.name === 'home' }" />
        </transition>
      </RouterView>
    </main>
  </div>
</template>

<style scoped>
.app-root {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: transparent;
  color: var(--color-text-primary);
  position: relative;
  z-index: 1;
}

/* 樱花粒子容器 */
.petal-container {
  position: fixed;
  top: 0; left: 0; width: 100%; height: 100%;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.petal {
  position: absolute;
  width: 14px; height: 14px;
  background: var(--color-sakura);
  border-radius: 50% 0 50% 0;
  top: -20px;
  animation: petal-fall linear infinite;
}

/* 导航栏 */
.top-nav {
  position: sticky;
  top: 0;
  z-index: 100;
}

/* 玻璃背景 */
.nav-glass {
  background: rgba(18, 10, 38, 0.04);
  backdrop-filter: blur(20px) saturate(150%);
  -webkit-backdrop-filter: blur(20px) saturate(150%);
  border-bottom: 1px solid transparent;
  background-image: linear-gradient(to right, transparent, rgba(255, 143, 177, 0.3), transparent);
  background-size: 100% 1px;
  background-position: bottom;
  background-repeat: no-repeat;
}

.nav-inner {
  max-width: 1280px;
  margin: 0 auto;
  padding: 10px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand {
  display: flex;
  align-items: center;
  text-decoration: none;
  line-height: 0;
}

.brand-glow {
  padding: 6px 10px;
  border-radius: var(--radius-md);
  background: radial-gradient(ellipse at center,
    rgba(255, 143, 177, 0.18) 0%,
    rgba(139, 92, 246, 0.10) 50%,
    transparent 100%);
  transition: background var(--dur-base) var(--ease-out);
}

.brand-glow:hover {
  background: radial-gradient(ellipse at center,
    rgba(255, 143, 177, 0.32) 0%,
    rgba(139, 92, 246, 0.18) 50%,
    transparent 100%);
}

.brand-logo {
  height: 38px;
  width: auto;
  display: block;
  border-radius: var(--radius-sm);
  transition: transform var(--dur-fast) var(--ease-out);
  filter: drop-shadow(0 0 8px rgba(255, 143, 177, 0.25));
}

.brand:hover .brand-logo {
  transform: scale(1.05);
}

/* 导航链接 */
.nav-links {
  display: flex;
  gap: 24px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: var(--text-sm);
  transition: color var(--dur-fast) var(--ease-out);
  position: relative;
  padding-bottom: 4px;
}

.nav-link i {
  font-size: 18px;
}

.nav-link:hover,
.nav-link.active {
  color: var(--color-sakura);
}

.nav-link.active::after {
  content: '';
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 2px;
  background: var(--color-sakura);
  border-radius: 1px;
  animation: indicator-slide var(--dur-base) var(--ease-spring);
}

/* 主内容区 */
.app-main {
  flex: 1;
  padding: 0;
  position: relative;
  z-index: 1;
  width: 100%;
}

.app-main > *:not(.full-page) {
  max-width: 1280px;
  margin: 0 auto;
}

/* home 页全屏 */
.full-page {
  max-width: none !important;
  margin: 0 !important;
}

/* 页面切换动画 */
.page-slide-enter-active {
  transition: opacity 350ms var(--ease-spring), transform 350ms var(--ease-spring);
}
.page-slide-leave-active {
  transition: opacity 200ms var(--ease-in), transform 200ms var(--ease-in);
}
.page-slide-enter-from {
  opacity: 0;
  transform: translateX(30px);
}
.page-slide-leave-to {
  opacity: 0;
  transform: translateX(-30px);
}

/* reduced-motion */
@media (prefers-reduced-motion: reduce) {
  .petal-container {
    display: none;
  }
  .page-slide-enter-active,
  .page-slide-leave-active {
    transition: opacity 200ms;
  }
  .page-slide-enter-from,
  .page-slide-leave-to {
    transform: none;
  }
}

/* 移动端 */
@media (max-width: 375px) {
  .nav-inner {
    padding: 8px 16px;
  }
  .brand-logo {
    height: 32px;
  }
  .nav-link {
    font-size: 12px;
  }
  .nav-link i {
    font-size: 16px;
  }
}
</style>
