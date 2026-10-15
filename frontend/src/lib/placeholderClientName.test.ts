import { describe, expect, it } from 'vitest'

import { isPlaceholderClientName } from './placeholderClientName'

describe('isPlaceholderClientName', () => {
  it('matches whole tokens including hyphenated names', () => {
    expect(isPlaceholderClientName('Unknown-Indian-Client')).toBe(true)
    expect(isPlaceholderClientName('n/a')).toBe(true)
    expect(isPlaceholderClientName('TBD')).toBe(true)
    expect(isPlaceholderClientName('test')).toBe(true)
    expect(isPlaceholderClientName('xxx')).toBe(true)
    expect(isPlaceholderClientName('client')).toBe(true)
  })

  it('does not match real names that only contain those letters', () => {
    expect(isPlaceholderClientName('Acme Corp')).toBe(false)
    expect(isPlaceholderClientName('Tina')).toBe(false)
    expect(isPlaceholderClientName('Northwind')).toBe(false)
  })
})
