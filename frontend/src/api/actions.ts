/**
 * Actions API（rollback）
 */
import { api } from './client'

// ============ Rollback ============

export async function rollbackProject(projectId: string, toChapter: number) {
  const { data } = await api.post(`/projects/${projectId}/rollback`, null, {
    params: { to_chapter: toChapter, confirm: true }
  })
  return data
}
