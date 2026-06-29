<script setup lang="ts">
/**
 * Home 启动页（少女梦幻风 · 游戏启动页风格）
 * 不需要用户操作，纯视觉入口页
 */
import { useRouter } from 'vue-router'
import heroImage from '@/assets/HOME-主图.png'
import logoImage from '@/assets/logo文字.png'

const router = useRouter()

const features = [
  { icon: 'sparkle', label: 'AI 共创' },
  { icon: 'globe', label: '多世界' },
  { icon: 'lightning', label: '实时生成' },
  { icon: 'scales', label: '探索度调节' },
]

// 漂浮气泡装饰
const floatingBubbles = [
  { size: 6, left: '8%', delay: '0s', duration: '8s' },
  { size: 10, left: '15%', delay: '2s', duration: '12s' },
  { size: 4, left: '25%', delay: '4s', duration: '10s' },
  { size: 8, left: '70%', delay: '1s', duration: '9s' },
  { size: 5, left: '85%', delay: '3s', duration: '11s' },
  { size: 7, left: '92%', delay: '5s', duration: '7s' },
  { size: 3, left: '45%', delay: '2.5s', duration: '13s' },
  { size: 6, left: '55%', delay: '6s', duration: '10s' },
]
</script>

<template>
  <div class="home-launch">
    <!-- 漂浮装饰气泡 -->
    <div class="deco-bubbles">
      <div
        v-for="(b, i) in floatingBubbles"
        :key="i"
        class="deco-bubble"
        :style="{
          width: b.size + 'px',
          height: b.size + 'px',
          left: b.left,
          animationDelay: b.delay,
          animationDuration: b.duration,
        }"
      ></div>
    </div>

    <!-- 装饰曲线 SVG -->
    <svg class="deco-curve deco-curve-top" viewBox="0 0 1440 200" preserveAspectRatio="none">
      <path d="M0,100 C360,180 720,20 1080,100 C1260,140 1380,80 1440,100 L1440,0 L0,0 Z"
        fill="none" stroke="rgba(255,143,177,0.08)" stroke-width="1" />
      <path d="M0,120 C360,200 720,40 1080,120 C1260,160 1380,100 1440,120 L1440,0 L0,0 Z"
        fill="none" stroke="rgba(139,92,246,0.06)" stroke-width="1" />
    </svg>

    <svg class="deco-curve deco-curve-bottom" viewBox="0 0 1440 200" preserveAspectRatio="none">
      <path d="M0,100 C360,20 720,180 1080,100 C1260,60 1380,120 1440,100 L1440,200 L0,200 Z"
        fill="none" stroke="rgba(255,143,177,0.08)" stroke-width="1" />
    </svg>

    <!-- 主图背景（铺满 + 轻微透明） -->
    <div class="hero-bg-layer">
      <img :src="heroImage" alt="" class="hero-bg-image" />
      <div class="hero-bg-overlay"></div>
    </div>

    <!-- 右上：我的世界 3D orb 气泡 -->
    <button class="orb-bubble" @click="router.push({ name: 'world-list' })" aria-label="我的世界">
      <!-- 环绕微小气泡 -->
      <span class="orbit-bubbles">
        <span class="orbit-bubble ob-1"></span>
        <span class="orbit-bubble ob-2"></span>
        <span class="orbit-bubble ob-3"></span>
        <span class="orbit-bubble ob-4"></span>
        <span class="orbit-bubble ob-5"></span>
      </span>
      <span class="orb-body">
        <span class="orb-highlight"></span>
        <span class="orb-text">我的世界</span>
      </span>
    </button>

    <!-- 主内容 -->
    <div class="launch-content">
      <!-- 顶部装饰线 -->
      <div class="deco-divider">
        <span class="deco-line"></span>
        <i class="ph ph-sparkle deco-star"></i>
        <span class="deco-line"></span>
      </div>

      <!-- LOGO 文字 -->
      <div class="logo-area">
        <img :src="logoImage" alt="小说·世界" class="logo-text" />
        <p class="logo-subtitle">让 AI 陪你写一个世界</p>
      </div>

      <!-- 启动新世界按钮 -->
      <button class="launch-btn" @click="router.push({ name: 'chat' })">
        <span class="launch-btn-bg"></span>
        <span class="launch-btn-content">
          <i class="ph ph-sparkle"></i>
          <span>启动新世界</span>
          <i class="ph ph-sparkle"></i>
        </span>
        <span class="launch-btn-particles">
          <span v-for="i in 6" :key="i" class="particle" :style="{ '--i': i }"></span>
        </span>
      </button>

      <!-- 底部装饰线 -->
      <div class="deco-divider">
        <span class="deco-line"></span>
        <i class="ph ph-feather deco-star"></i>
        <span class="deco-line"></span>
      </div>

      <!-- 特性说明 -->
      <div class="features">
        <div v-for="f in features" :key="f.label" class="feature-item">
          <i :class="`ph ph-${f.icon}`"></i>
          <span>{{ f.label }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-launch {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 0;
}

/* ===== 装饰气泡 ===== */
.deco-bubbles {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}
.deco-bubble {
  position: absolute;
  bottom: -20px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 143, 177, 0.3), transparent 70%);
  animation: bubble-float linear infinite;
}
@keyframes bubble-float {
  0% {
    transform: translateY(0) scale(0.8);
    opacity: 0;
  }
  10% {
    opacity: 1;
  }
  90% {
    opacity: 0.6;
  }
  100% {
    transform: translateY(-100vh) scale(1.2);
    opacity: 0;
  }
}

/* ===== 装饰曲线 ===== */
.deco-curve {
  position: absolute;
  width: 100%;
  height: 200px;
  z-index: 0;
  pointer-events: none;
}
.deco-curve-top {
  top: 0;
  left: 0;
}
.deco-curve-bottom {
  bottom: 0;
  left: 0;
}

/* ===== 主图背景层 ===== */
.hero-bg-layer {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
}
.hero-bg-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.55;
  filter: blur(1px) brightness(0.8);
}
.hero-bg-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom,
    rgba(18, 10, 38, 0.3) 0%,
    rgba(18, 10, 38, 0.5) 50%,
    rgba(18, 10, 38, 0.7) 100%);
  pointer-events: none;
}

/* ===== 右上 3D orb 气泡 ===== */
.orb-bubble {
  position: absolute;
  top: 32px;
  right: 12%;
  z-index: 10;
  width: 110px;
  height: 110px;
  border: none;
  cursor: pointer;
  background: transparent;
  padding: 0;
  animation: orb-float 4s ease-in-out infinite;
  transition: transform var(--dur-base) var(--ease-spring);
}

/* orb 主体 */
.orb-body {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background:
    radial-gradient(circle at 35% 28%,
      rgba(255, 255, 255, 0.7) 0%,
      rgba(255, 200, 220, 0.5) 12%,
      rgba(255, 143, 177, 0.45) 40%,
      rgba(180, 80, 130, 0.4) 75%,
      rgba(80, 20, 50, 0.35) 100%);
  box-shadow:
    inset 0 -8px 16px rgba(120, 30, 60, 0.4),
    inset 0 4px 12px rgba(255, 255, 255, 0.25),
    0 12px 28px rgba(255, 143, 177, 0.35),
    0 4px 8px rgba(0, 0, 0, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--dur-base) var(--ease-spring);
}

/* orb 高光 */
.orb-highlight {
  position: absolute;
  top: 12%;
  left: 28%;
  width: 30%;
  height: 22%;
  border-radius: 50%;
  background: radial-gradient(ellipse, rgba(255, 255, 255, 0.7), transparent 70%);
  pointer-events: none;
}

.orb-text {
  position: relative;
  z-index: 1;
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: 600;
  font-family: var(--font-display);
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.5);
  white-space: nowrap;
  pointer-events: none;
}

/* 交互 */
.orb-bubble:hover {
  transform: scale(1.08);
}
.orb-bubble:hover .orb-body {
  box-shadow:
    inset 0 -8px 16px rgba(120, 30, 60, 0.5),
    inset 0 4px 12px rgba(255, 255, 255, 0.35),
    0 16px 36px rgba(255, 143, 177, 0.5),
    0 6px 12px rgba(0, 0, 0, 0.25);
  filter: brightness(1.15) saturate(1.2);
}
.orb-bubble:active {
  transform: scale(0.95);
  transition: transform 100ms var(--ease-in);
}

/* focus ring */
.orb-bubble:focus-visible {
  outline: 2px solid var(--color-sakura);
  outline-offset: 6px;
}

/* ===== 环绕微小气泡 ===== */
.orbit-bubbles {
  position: absolute;
  inset: -20px;
  z-index: 0;
  pointer-events: none;
  animation: orbit-rotate 12s linear infinite;
}
@keyframes orbit-rotate {
  to { transform: rotate(360deg); }
}

.orbit-bubble {
  position: absolute;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%,
    rgba(255, 255, 255, 0.6),
    rgba(255, 143, 177, 0.4) 60%,
    rgba(139, 92, 246, 0.2));
  box-shadow:
    inset 0 -1px 2px rgba(255, 100, 140, 0.3),
    inset 0 1px 2px rgba(255, 255, 255, 0.4),
    0 2px 6px rgba(255, 143, 177, 0.2);
}

.ob-1 { width: 10px; height: 10px; top: 0; left: 50%; transform: translateX(-50%); }
.ob-2 { width: 7px; height: 7px; top: 30%; right: -4px; }
.ob-3 { width: 12px; height: 12px; bottom: 10%; right: 8%; }
.ob-4 { width: 6px; height: 6px; bottom: -2px; left: 30%; }
.ob-5 { width: 9px; height: 9px; top: 20%; left: -4px; }

@keyframes orb-float {
  0%, 100% { transform: translateY(0) rotate(-2deg); }
  50% { transform: translateY(-10px) rotate(2deg); }
}

/* ===== 主内容 ===== */
.launch-content {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-5);
  padding: var(--space-5);
  max-width: 900px;
  width: 100%;
  justify-content: center;
  height: 100%;
}

/* ===== LOGO 文字 ===== */
.logo-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
}
.logo-text {
  height: 330px;
  width: auto;
  opacity: 0.95;
  filter: drop-shadow(0 0 16px rgba(255, 143, 177, 0.35));
  animation: logo-glow 3s ease-in-out infinite;
}
@keyframes logo-glow {
  0%, 100% {
    filter: drop-shadow(0 0 12px rgba(255, 143, 177, 0.25));
  }
  50% {
    filter: drop-shadow(0 0 24px rgba(255, 143, 177, 0.5));
  }
}
.logo-subtitle {
  font-family: var(--font-display);
  font-size: var(--text-lg);
  color: var(--color-text-secondary);
  letter-spacing: 4px;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
  margin: 0;
  opacity: 0.8;
}

/* ===== 装饰分隔线 ===== */
.deco-divider {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 280px;
}
.deco-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 143, 177, 0.3), transparent);
}
.deco-star {
  font-size: 14px;
  color: var(--color-sakura);
  opacity: 0.7;
  animation: sparkle-twinkle 2s ease-in-out infinite;
}

/* ===== 启动新世界按钮 ===== */
.launch-btn {
  position: relative;
  padding: 18px 56px;
  border: none;
  border-radius: var(--radius-full);
  cursor: pointer;
  overflow: visible;
  isolation: isolate;
  margin-top: var(--space-3);
  animation: btn-float 4s ease-in-out infinite;
}
@keyframes btn-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}
.launch-btn-bg {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-sakura), var(--color-violet), var(--color-sakura));
  background-size: 200% 200%;
  animation: gradient-shift 3s ease infinite;
  z-index: 0;
}
@keyframes gradient-shift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}
.launch-btn::before {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-sakura), var(--color-violet));
  opacity: 0.4;
  filter: blur(12px);
  z-index: -1;
  animation: glow-pulse 2s ease-in-out infinite;
}
@keyframes glow-pulse {
  0%, 100% { opacity: 0.3; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.08); }
}
.launch-btn-content {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: #fff;
  font-size: var(--text-xl);
  font-weight: 700;
  font-family: var(--font-display);
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  letter-spacing: 2px;
}
.launch-btn-content i {
  font-size: 22px;
  animation: sparkle-twinkle 1.5s ease-in-out infinite;
}
.launch-btn-content i:last-child {
  animation-delay: 0.75s;
}
@keyframes sparkle-twinkle {
  0%, 100% { opacity: 0.6; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.2); }
}
.launch-btn:hover .launch-btn-bg {
  filter: brightness(1.15);
}
.launch-btn:hover::before {
  opacity: 0.7;
  transform: scale(1.12);
}
.launch-btn:active {
  transform: scale(0.95);
  transition: transform 100ms var(--ease-in);
}

/* 按钮粒子 */
.launch-btn-particles {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 2;
}
.particle {
  position: absolute;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--color-sakura-light);
  top: 50%;
  left: 50%;
  opacity: 0;
  animation: particle-burst 2s ease-out infinite;
  animation-delay: calc(var(--i) * 0.3s);
}
@keyframes particle-burst {
  0% {
    transform: translate(-50%, -50%) translate(0, 0);
    opacity: 0;
  }
  20% {
    opacity: 1;
  }
  100% {
    transform: translate(-50%, -50%) translate(
      calc(cos(calc(var(--i) * 60deg)) * 60px),
      calc(sin(calc(var(--i) * 60deg)) * 60px)
    );
    opacity: 0;
  }
}

/* ===== 特性说明 ===== */
.features {
  display: flex;
  gap: var(--space-6);
  flex-wrap: wrap;
  justify-content: center;
  margin-top: var(--space-3);
}
.feature-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  opacity: 0.7;
  transition: opacity var(--dur-base);
}
.feature-item:hover {
  opacity: 1;
}
.feature-item i {
  font-size: 16px;
  color: var(--color-sakura);
}

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .hero-image {
    max-height: 35vh;
  }
  .launch-btn {
    padding: 14px 40px;
  }
  .launch-btn-content {
    font-size: var(--text-lg);
  }
  .features {
    gap: var(--space-4);
  }
}

@media (max-width: 375px) {
  .hero-image {
    max-height: 30vh;
    border-radius: var(--radius-md);
  }
  .logo-text {
    height: 80px;
  }
  .logo-subtitle {
    font-size: var(--text-sm);
    letter-spacing: 2px;
  }
  .deco-divider {
    width: 200px;
  }
  .launch-btn {
    padding: 12px 32px;
  }
  .launch-btn-content {
    font-size: var(--text-base);
  }
  .feature-item {
    font-size: var(--text-xs);
  }
  .orb-bubble {
    right: 5%;
    width: 80px;
    height: 80px;
  }
  .orb-text {
    font-size: var(--text-xs);
  }
}

/* ===== reduced-motion ===== */
@media (prefers-reduced-motion: reduce) {
  .deco-bubble,
  .hero-bg-image,
  .logo-text,
  .deco-star,
  .launch-btn::before,
  .launch-btn-bg,
  .particle,
  .orb-bubble,
  .orbit-bubbles {
    animation: none !important;
  }
  .particle {
    display: none;
    display: none;
  }
}
</style>
