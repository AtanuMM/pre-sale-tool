import { describe, expect, it } from 'vitest'

import { anyStepGenerating } from '@/api/steps'
import type { ProjectStep } from '@/api/steps'

function step(status: ProjectStep['status']): ProjectStep {
  return {
    key: 'scope_analysis',
    title: 'Scope analysis',
    order: 1,
    implemented: true,
    status,
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
  }
}

describe('anyStepGenerating', () => {
  it('is true only while a step is generating', () => {
    expect(anyStepGenerating(undefined)).toBe(false)
    expect(anyStepGenerating([step('ready')])).toBe(false)
    expect(anyStepGenerating([step('generating')])).toBe(true)
    expect(anyStepGenerating([step('in_review'), step('generating')])).toBe(true)
  })
})
