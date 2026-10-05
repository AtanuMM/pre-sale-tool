export const THEME_STORAGE_KEY = 'scopedesk-theme'

export type ThemeMode = 'light' | 'dark'

export function readStoredTheme(): ThemeMode | null {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY)
    if (value === 'light' || value === 'dark') {
      return value
    }
  } catch {
    /* private mode / blocked storage */
  }
  return null
}

export function writeStoredTheme(theme: ThemeMode): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    /* ignore */
  }
}

export function applyThemeClass(theme: ThemeMode): void {
  const root = document.documentElement
  if (theme === 'dark') {
    root.classList.add('dark')
  } else {
    root.classList.remove('dark')
  }
}

export function resolveInitialTheme(): ThemeMode {
  const stored = readStoredTheme()
  return stored ?? 'light'
}
