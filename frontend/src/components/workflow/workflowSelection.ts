import type { ProjectStep } from '@/api/steps'

export function pickDefaultStepKey(steps: ProjectStep[]): string {
  if (steps.length === 0) return 'scope_analysis'
  const sorted = [...steps].sort((a, b) => a.order - b.order)
  const needsAction = sorted.find(
    (s) => s.status === 'generating' || s.status === 'in_review',
  )
  if (needsAction) return needsAction.key
  const ready = sorted.find((s) => s.status === 'ready')
  if (ready) return ready.key
  let lastApproved: ProjectStep | null = null
  for (const step of sorted) {
    if (step.status === 'approved') lastApproved = step
  }
  if (lastApproved) return lastApproved.key
  return sorted[0]?.key ?? 'scope_analysis'
}

export function generationStartIso(
  detail: { generation_started_at: string | null; created_at: string } | null | undefined,
  latest: { created_at: string } | null | undefined,
): string | null {
  if (detail?.generation_started_at) return detail.generation_started_at
  if (latest?.created_at) return latest.created_at
  return null
}
