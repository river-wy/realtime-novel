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
  // v0.8.3: 项目状态（v0.6.2 去掉 onboarding_step 判断逻辑，保留 status 展示）
  status: 'not_started' | 'in_progress' | 'completed'
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
  // v0.9: 世界封面图
  cover_image_url?: string | null
  // v007 C2: POV 角色（current_pov 存 char_id，分拆为 char_id + name）
  current_pov?: string | null          // char_id（兼容旧字段）
  current_pov_char_id?: string | null  // 明确语义：char_id
  current_pov_name?: string | null     // 展示用 name
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
