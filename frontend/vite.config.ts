import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

/**
 * realtime-novel 前端 Vite 配置
 *
 * 端口约定（v0.6 起，hardcoded 写在配置里供前端开发查阅）：
 * - 前端 dev server:  7777
 * - 后端 API:         7778  （uvicorn backend.api.app:app --port 7778）
 * - API 代理：        /api → http://127.0.0.1:7778
 *
 * 调整端口：改下面两个常量 + 同步改 scripts/start.sh。
 */

// 端口常量（前端 dev server + 后端 API 目标）
const FRONTEND_PORT = 7777
const BACKEND_PORT = 7778

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: FRONTEND_PORT,
    strictPort: true,  // 端口被占就报错（避免静默换端口）
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${BACKEND_PORT}`,
        changeOrigin: true,
        ws: true
      },
      '/openapi.json': {
        target: `http://127.0.0.1:${BACKEND_PORT}`,
        changeOrigin: true
      }
    }
  }
})
