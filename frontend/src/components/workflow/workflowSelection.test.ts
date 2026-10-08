import { describe, expect, it } from 'vitest'

import type { ProjectStep } from '@/api/steps'
import { pickDefaultStepKey } from '@/components/workflow/workflowSelection'

function step(partial: Partial<ProjectStep> & { key: string; order: number }): ProjectStep {
  return {
    title: partial.key,
    implemented: true,
    status: 'locked',
    has_failed_attempt: false,
    can_generate: false,
    blocked_reason: null,
    current_version_id: null,
    can_request_changes: false,
    can_approve: false,
    approve_blocked_reason: null,
    latest_version: null,
    layout: [],
    reads_description: '',
    writes_description: '',
    context_steps: [],
    ...partial,
  }
}

describe('pickDefaultStepKey', () => {
  it('prefers generating then in_review then ready then last approved', () => {
    const steps = [
      step({ key: 'scope_analysis', order: 1, status: 'approved' }),
      step({ key: 'gap_analysis', order: 2, status: 'in_review' }),
    ]
    expect(pickDefaultStepKey(steps)).toBe('gap_analysis')
  })

  it('picks ready when nothing in flight', () => {
    const steps = [
      step({ key: 'scope_analysis', order: 1, status: 'approved' }),
      step({ key: 'gap_analysis', order: 2, status: 'ready' }),
    ]
    expect(pickDefaultStepKey(steps)).toBe('gap_analysis')
  })
})
