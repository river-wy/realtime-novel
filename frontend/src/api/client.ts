/**
 * Axios 客户端
 * baseURL: /api（Vite proxy 转发到后端）
 * 后端实际端口：见 vite.config.ts 的 BACKEND_PORT（当前 7777）
 * 不要在这里硬编码后端端口 — 走 /api 代理路径
 */
import axios, { type AxiosInstance, type AxiosError } from 'axios'

export const api: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 120_000,  // 章节生成最多 120s
  headers: {
    'Content-Type': 'application/json'
  }
})

// 响应拦截器：提取后端 detail
api.interceptors.response.use(
  response => response,
  (error: AxiosError) => {
    const detail = (error.response?.data as { detail?: string })?.detail
    if (detail) {
      error.message = detail
    }
    return Promise.reject(error)
  }
)

/** 健康检查 */
export async function healthCheck() {
  const { data } = await api.get('/health')
  return data
}
