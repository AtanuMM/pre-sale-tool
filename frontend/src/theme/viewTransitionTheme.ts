export type ThemeTransitionOrigin = {
  x: number
  y: number
}

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

type DocumentWithViewTransition = Document & {
  startViewTransition?: (updateCallback: () => void | Promise<void>) => {
    finished: Promise<void>
  }
}

const THEME_TRANSITION_MS = 300

export function applyThemeWithTransition(
  updateDom: () => void,
  origin?: ThemeTransitionOrigin,
): void {
  if (prefersReducedMotion()) {
    updateDom()
    return
  }

  const root = document.documentElement

  if (origin) {
    root.style.setProperty('--theme-switch-x', `${origin.x}px`)
    root.style.setProperty('--theme-switch-y', `${origin.y}px`)
  }

  const doc = document as DocumentWithViewTransition

  if (typeof doc.startViewTransition !== 'function') {
    root.classList.add('theme-transition')
    updateDom()
    window.setTimeout(() => {
      root.classList.remove('theme-transition')
    }, THEME_TRANSITION_MS)
    return
  }

  doc.startViewTransition(() => {
    updateDom()
  })
}
