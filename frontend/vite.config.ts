import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

/**
 * realtime-novel 前端 Vite 配置
 *
 * 端口约定（v0.6 起，hardcoded 写在配置里供前端开发查阅）：
 * - 前端 dev server:  5174
 * - 后端 API:         7777  （uvicorn realtime_novel.api.app:app --port 7777）
 * - API 代理：        /api → http://127.0.0.1:7777
 *
 * 注意：5173 端口被 lunaris 自己的 vite 占着（pid 91292），
 *       所以 frontend 用 5174 避开冲突。
 *       后端用 7777（避开 8080 默认）作为业务端口。
 *
 * 调整端口：改下面两个常量。
 */

// 端口常量（前端 dev server + 后端 API 目标）
const FRONTEND_PORT = 5174
const BACKEND_PORT = 7777

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
        changeOrigin: true
      },
      '/openapi.json': {
        target: `http://127.0.0.1:${BACKEND_PORT}`,
        changeOrigin: true
      }
    }
  }
})
