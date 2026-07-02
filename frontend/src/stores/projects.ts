/**
 * Projects Pinia store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/api/projects'

export const useProjectsStore = defineStore('projects', () => {
  const projects = ref<api.ProjectInfo[]>([])
  const total = ref(0)
  const current = ref<api.ProjectDetail | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadList(limit = 50) {
    loading.value = true
    error.value = null
    try {
      const r = await api.listProjects(limit)
      projects.value = r.projects
      total.value = r.total
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function loadOne(id: string) {
    loading.value = true
    error.value = null
    try {
      current.value = await api.getProject(id)
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function create(name: string, initialPrompt?: string) {
    const r = await api.createProject(name, initialPrompt)
    await loadList()
    return r
  }

  async function remove(id: string) {
    const r = await api.deleteProject(id)
    // 本地立即过滤掉, 再后台刷新
    projects.value = projects.value.filter(p => p.id !== id)
    total.value = Math.max(0, total.value - 1)
    await loadList()
    return r
  }

  /** 切换项目探索度 */
  async function updateExplorationLevel(id: string, level: 'conservative' | 'standard' | 'wild') {
    const r = await api.updateExplorationLevel(id, level)
    // 更新本地缓存
    await loadOne(id)
    await loadList()
    return r
  }

  const hasCurrent = computed(() => current.value !== null)

  return {
    projects, total, current, loading, error, hasCurrent,
    loadList, loadOne, create, remove, updateExplorationLevel,
  }
})
