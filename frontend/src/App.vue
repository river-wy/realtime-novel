<script setup lang="ts">
import { RouterView, RouterLink } from 'vue-router'
import logoImage from '@/assets/左上-logo.png'
</script>

<template>
  <div class="app-root">
    <nav class="top-nav">
      <div class="nav-inner">
        <RouterLink to="/" class="brand">
          <img :src="logoImage" alt="realtime-novel logo" class="brand-logo" />
          <span>realtime-novel</span>
        </RouterLink>
        <div class="nav-links">
          <RouterLink to="/">首页</RouterLink>
          <RouterLink to="/onboarding">新世界</RouterLink>
          <RouterLink to="/world/demo-urban-romance">世界</RouterLink>
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
  gap: var(--space-2);
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-weight: 700;
  font-size: 20px;
  color: var(--color-accent-1);
  text-decoration: none;
}

.brand-logo {
  height: 32px;
  width: auto;
  display: block;
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
