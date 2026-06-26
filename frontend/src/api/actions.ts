/**
 * Actions API（interventions / rollback / image）
 *
 * v0.6.2: 刪除 Onboarding 相关函数（onboardingStep）
 * 项目 onboard 创建全部走管家 Agent 对接
 */
import { api } from './client'

// ============ Interventions ============

export async function submitIntervention(
  projectId: string,
  intervention?: string,
  actorFeedback?: string,
  actorCharacter?: string
) {
  const { data } = await api.post(`/projects/${projectId}/interventions`, {
    intervention,
    actor_feedback: actorFeedback,
    actor_character: actorCharacter
  })
  return data
}

// ============ Rollback ============

export async function rollbackProject(projectId: string, toChapter: number) {
  const { data } = await api.post(`/projects/${projectId}/rollback`, null, {
    params: { to_chapter: toChapter, confirm: true }
  })
  return data
}

// ============ Image ============

export async function generateImage(projectId: string, styleHint?: string) {
  const { data } = await api.post(`/projects/${projectId}/image`, { style_hint: styleHint })
  return data
}
