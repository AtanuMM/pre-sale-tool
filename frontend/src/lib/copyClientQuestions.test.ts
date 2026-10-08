import { describe, expect, it } from 'vitest'

import { formatClientQuestions } from '@/lib/copyClientQuestions'

describe('formatClientQuestions', () => {
  it('formats numbered questions with why it matters', () => {
    const text = formatClientQuestions([
      { question: 'Which SSO?', why_it_matters: 'Auth design' },
      { question: 'Timeline?', why_it_matters: '' },
    ])
    expect(text).toContain('1. Which SSO?')
    expect(text).toContain('Why it matters: Auth design')
    expect(text).toContain('2. Timeline?')
  })
})
