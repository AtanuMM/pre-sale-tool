import { describe, expect, it } from 'vitest'

import { generationFailureHint } from './generationFailureHints'

describe('generationFailureHint', () => {
  it('maps known failure codes', () => {
    expect(generationFailureHint('llm_schema_rejected')).toMatch(/response format/i)
    expect(generationFailureHint('generation_timeout')).toMatch(/too long/i)
  })

  it('returns null for unknown or empty codes', () => {
    expect(generationFailureHint(undefined)).toBeNull()
    expect(generationFailureHint('')).toBeNull()
    expect(generationFailureHint('something_else')).toBeNull()
  })
})
