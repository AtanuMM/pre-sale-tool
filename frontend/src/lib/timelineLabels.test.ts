import { describe, expect, it } from 'vitest'

import { timelineActionLabel } from '@/lib/timelineLabels'

describe('timelineActionLabel', () => {
  it('maps known actions', () => {
    expect(timelineActionLabel('project.created')).toBe('Project created')
    expect(timelineActionLabel('step.approved')).toBe('Step approved')
    expect(timelineActionLabel('prompt.viewed')).toBe('Prompt viewed (logged)')
  })

  it('labels document downloads', () => {
    expect(timelineActionLabel('document.downloaded')).toBe('Document downloaded')
  })

  it('falls back for unknown actions', () => {
    const label = timelineActionLabel('some.unknown.event')
    expect(label.length).toBeGreaterThan(0)
    expect(label).not.toBe('')
  })
})
