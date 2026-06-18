/**
 * Actions API（onboarding / interventions / rollback / image）
 */
import { api } from './client'

// ============ Onboarding ============

export type OnboardingStep = '1a' | '1b' | '2' | '3' | '4' | '5'

export interface OnboardingResult {
  step: string
  result: Record<string, any>
  next_step: string | null
}

export async function onboardingStep(
  projectId: string,
  step: OnboardingStep,
  payload: Record<string, any> = {}
): Promise<OnboardingResult> {
  const { data } = await api.post(`/projects/${projectId}/onboarding`, { step, payload })
  return data
}

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
