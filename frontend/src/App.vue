<script setup lang="ts">
import { RouterView, RouterLink } from 'vue-router'
import mainImage from '@/assets/首页-主图.png'
</script>

<template>
  <div class="app-root">
    <nav class="top-nav">
      <div class="nav-inner">
        <RouterLink to="/" class="brand">
          <div class="brand-glow">
            <img :src="mainImage" alt="realtime-novel" class="brand-logo" />
          </div>
        </RouterLink>
        <div class="nav-links">
          <RouterLink to="/">首页</RouterLink>
          <RouterLink to="/onboarding">新世界</RouterLink>
          <RouterLink to="/worlds">世界</RouterLink>
        </div>
      </div>
    </nav>

    <main class="app-main">
      <RouterView v-slot="{ Component, route }">
        <transition name="fade" mode="out-in">
          <component :is="Component" :key="route.fullPath" />
        </transition>
      </RouterView>
    </main>
  </div>
</template>

<style scoped>
.app-root {
  min-height: 100vh;
  background: var(--color-night-1);
  color: var(--color-text);
}

.top-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(27, 15, 46, 0.85);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--color-night-3);
}

.nav-inner {
  max-width: 1280px;
  margin: 0 auto;
  padding: 16px 24px;
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

/* 渐变光晕容器：让透明 PNG 融进深紫底 */
.brand-glow {
  padding: 6px 10px;
  border-radius: var(--radius-md);
  background:
    radial-gradient(ellipse at center,
      rgba(255, 143, 177, 0.18) 0%,
      rgba(139, 92, 246, 0.10) 50%,
      transparent 100%
    );
  transition: background var(--motion-base) var(--ease-out);
}

.brand-glow:hover {
  background:
    radial-gradient(ellipse at center,
      rgba(255, 143, 177, 0.32) 0%,
      rgba(139, 92, 246, 0.18) 50%,
      transparent 100%
    );
}

.brand-logo {
  height: 48px;
  width: auto;
  display: block;
  border-radius: var(--radius-sm);
  transition: transform var(--motion-fast) var(--ease-out);
  filter: drop-shadow(0 0 8px rgba(255, 143, 177, 0.25));
}

.brand:hover .brand-logo {
  transform: scale(1.05);
}

.nav-links {
  display: flex;
  gap: 24px;
}

.nav-links a {
  color: var(--color-text-dim);
  text-decoration: none;
  font-size: 14px;
  transition: color 0.2s;
}

.nav-links a:hover,
.nav-links a.router-link-active {
  color: var(--color-accent-2);
}

.app-main {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
