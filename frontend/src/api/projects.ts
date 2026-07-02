/**
 * Projects API（5 端点）
 */
import {api} from './client'

export interface ProjectInfo {
  id: string
  name: string
  exploration_level: 'conservative' | 'standard' | 'wild'
  chapter_count: number
  last_updated: string | null
  status: 'not_started' | 'in_progress' | 'completed'
  cover_image_url?: string | null
}

export interface ProjectDetail {
  id: string
  name: string
  exploration_level: 'conservative' | 'standard' | 'wild'
  seven_artifacts: Record<string, any> | null
  world_tree: Record<string, any> | null
  chapters: ChapterSummary[] | null
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

export async function createProject(name: string, initialPrompt?: string) {
  const { data } = await api.post('/projects', { name, initial_prompt: initialPrompt })
  return data
}

export async function deleteProject(id: string) {
  const { data } = await api.delete(`/projects/${id}`, { params: { confirm: true } })
  return data
}

/**
 * 切换项目探索度 (conservative/standard/wild)
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
