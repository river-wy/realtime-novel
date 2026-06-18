/**
 * Chapters API
 */
import { api } from './client'
import type { ChapterSummary } from './projects'

export interface ChapterListItem extends Omit<ChapterSummary, 'time'> {
  status: string
  time?: string | null
}

export interface ChapterContent {
  num: number
  title: string
  content: string
  word_count: number
  generated_at: string | null
}

export interface GenerateChapterResult {
  chapter_num: number
  title: string
  content: string
  word_count: number
  generated_at: string
  new_seeds_triggered: number
  /** v0.5 新增：1 句话 summary */
  summary: string
}

export async function listChapters(projectId: string): Promise<{ chapters: ChapterListItem[] }> {
  const { data } = await api.get(`/projects/${projectId}/chapters`)
  return data
}

export async function readChapter(projectId: string, n: number): Promise<ChapterContent> {
  const { data } = await api.get(`/projects/${projectId}/chapters/${n}`)
  return data
}

export async function generateChapter(
  projectId: string,
  options?: { intervention?: string; actor_feedback?: string; actor_character?: string }
): Promise<GenerateChapterResult> {
  const { data } = await api.post(`/projects/${projectId}/chapters`, options || {})
  return data
}
