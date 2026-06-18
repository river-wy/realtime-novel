/**
 * Axios 客户端
 * baseURL: /api（Vite proxy 转发到 http://127.0.0.1:8080/api）
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
