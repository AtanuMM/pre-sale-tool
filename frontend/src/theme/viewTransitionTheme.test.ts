import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { applyThemeWithTransition, prefersReducedMotion } from './viewTransitionTheme'

describe('viewTransitionTheme', () => {
  beforeEach(() => {
    document.documentElement.classList.remove('theme-transition', 'dark')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('skips animation when reduced motion is preferred', () => {
    vi.spyOn(window, 'matchMedia').mockImplementation((query: string) => ({
      matches: query.includes('reduce'),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }))
    expect(prefersReducedMotion()).toBe(true)
    const update = vi.fn()
    applyThemeWithTransition(update)
    expect(update).toHaveBeenCalledOnce()
    expect(document.documentElement.classList.contains('theme-transition')).toBe(false)
  })

  it('uses startViewTransition when available', () => {
    vi.spyOn(window, 'matchMedia').mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }))
    const update = vi.fn()
    const startViewTransition = vi.fn((cb: () => void) => {
      cb()
      return {
        finished: Promise.resolve(),
        ready: Promise.resolve(),
        updateCallbackDone: Promise.resolve(),
        types: new Set<string>(),
        skipTransition: () => {},
      }
    })
    document.startViewTransition = startViewTransition as typeof document.startViewTransition
    applyThemeWithTransition(update, { x: 10, y: 20 })
    expect(startViewTransition).toHaveBeenCalledOnce()
    expect(update).toHaveBeenCalledOnce()
    Reflect.deleteProperty(document, 'startViewTransition')
  })

  it('falls back to theme-transition class without API', () => {
    vi.useFakeTimers()
    vi.spyOn(window, 'matchMedia').mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }))
    Reflect.deleteProperty(document, 'startViewTransition')
    applyThemeWithTransition(() => {
      document.documentElement.classList.add('dark')
    })
    expect(document.documentElement.classList.contains('theme-transition')).toBe(true)
    vi.advanceTimersByTime(300)
    expect(document.documentElement.classList.contains('theme-transition')).toBe(false)
    vi.useRealTimers()
  })
})
