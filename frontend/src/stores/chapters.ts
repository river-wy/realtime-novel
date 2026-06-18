/**
 * Chapters Pinia store（含 v0.5 summary 自动展示）
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/api/chapters'

export const useChaptersStore = defineStore('chapters', () => {
  const list = ref<api.ChapterListItem[]>([])
  const current = ref<api.ChapterContent | null>(null)
  /** v0.5 新增：当前章节 1 句 summary */
  const currentSummary = ref<string | null>(null)
  const loading = ref(false)
  const generating = ref(false)
  const error = ref<string | null>(null)

  async function loadList(projectId: string) {
    loading.value = true
    error.value = null
    try {
      const r = await api.listChapters(projectId)
      list.value = r.chapters
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function loadOne(projectId: string, n: number) {
    loading.value = true
    error.value = null
    try {
      current.value = await api.readChapter(projectId, n)
      // 同步设置 summary（从 list 拿）
      const item = list.value.find(c => c.num === n)
      currentSummary.value = item?.summary || null
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function generate(
    projectId: string,
    options?: { intervention?: string; actor_feedback?: string; actor_character?: string }
  ) {
    generating.value = true
    error.value = null
    try {
      const r = await api.generateChapter(projectId, options)
      // 刷新列表 + 加载新章节
      await loadList(projectId)
      await loadOne(projectId, r.chapter_num)
      return r
    } catch (e: any) {
      error.value = e.message
      throw e
    } finally {
      generating.value = false
    }
  }

  const count = computed(() => list.value.length)
  const latest = computed(() => list.value[0] || null)

  return { list, current, currentSummary, loading, generating, error, count, latest, loadList, loadOne, generate }
})
