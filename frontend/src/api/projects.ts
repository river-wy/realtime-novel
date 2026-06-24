/**
 * Projects API（5 端点）
 */
import {api} from './client'

export interface ProjectInfo {
  id: string
  name: string
  palette: string
  // v0.8: 探索度
  exploration_level: 'conservative' | 'standard' | 'wild'
  chapter_count: number
  last_updated: string | null
  // v0.8.3: onboard 续接用
  onboarding_step: number | null  // null=从未进过, 0=未开始, 1-4=进行中
  status: 'not_started' | 'in_progress' | 'completed'  // v0.8.3
  // v0.9: 世界封面图
  cover_image_url?: string | null
}

export interface ProjectDetail {
  id: string
  name: string
  palette: string
  // v0.8: 探索度
  exploration_level: 'conservative' | 'standard' | 'wild'
  seven_artifacts: Record<string, any> | null
  world_tree: Record<string, any> | null
  chapters: ChapterSummary[] | null
  // v0.8.3: onboard 续接用
  onboarding_step?: number | null
  // 续接回填用：已保存的所有 payload 字段（genres/styles/tone/palette/story_core/...）
  onboarding_payload?: Record<string, any> | null
  // v0.9: 世界封面图
  cover_image_url?: string | null
}

export interface ChapterSummary {
  num: number
  title: string
  summary?: string | null
  word_count?: number
  file_path?: string
  time?: string
}

export async function listProjects(limit = 20, offset = 0): Promise<{ total: number; projects: ProjectInfo[] }> {
  const { data } = await api.get('/projects', { params: { limit, offset } })
  return data
}

export async function getProject(id: string): Promise<ProjectDetail> {
  const { data } = await api.get(`/projects/${id}`)
  return data
}

export async function createProject(name: string, palette: string, initialPrompt?: string) {
  const { data } = await api.post('/projects', { name, palette, initial_prompt: initialPrompt })
  return data
}

export async function deleteProject(id: string) {
  const { data } = await api.delete(`/projects/${id}`, { params: { confirm: true } })
  return data
}

export async function updateBase(
  projectId: string,
  key: string,
  newValue: string
) {
  const { data } = await api.patch(`/projects/${projectId}/base`, { key, new_value: newValue })
  return data
}

/**
 * v0.8: 切换项目探索度 (conservative/standard/wild)
 */
export async function updateExplorationLevel(
  projectId: string,
  level: 'conservative' | 'standard' | 'wild'
) {
  const { data } = await api.patch(`/projects/${projectId}/exploration-level`, {
    exploration_level: level,
  })
  return data as { project_id: string; exploration_level: string; message: string }
}
