import type { DerivedStepStatus, StepVersionSource, StepVersionStatus } from '@/api/steps'

const DERIVED_LABELS: Record<DerivedStepStatus, string> = {
  locked: 'Locked',
  ready: 'Ready',
  generating: 'Generating',
  in_review: 'In review',
  approved: 'Approved',
  stale: 'Stale',
}

const VERSION_STATUS_LABELS: Record<StepVersionStatus, string> = {
  queued: 'Queued',
  generating: 'Generating',
  in_review: 'In review',
  approved: 'Approved',
  failed: 'Failed',
  changes_requested: 'Changes requested',
  superseded: 'Superseded',
  stale: 'Stale',
}

export function derivedStepStatusLabel(status: DerivedStepStatus): string {
  return DERIVED_LABELS[status]
}

export function versionStatusLabel(status: StepVersionStatus): string {
  return VERSION_STATUS_LABELS[status]
}

export function versionSourceLabel(source: StepVersionSource): string {
  switch (source) {
    case 'generated':
      return 'Generated'
    case 'manual_edit':
      return 'Manual edit'
    case 'section_regen':
      return 'Section regen'
    default:
      return source
  }
}

export function formatGenerationElapsed(startIso: string): string {
  const startMs = new Date(startIso).getTime()
  if (Number.isNaN(startMs)) return '0:00'
  const totalSec = Math.max(0, Math.floor((Date.now() - startMs) / 1000))
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}
