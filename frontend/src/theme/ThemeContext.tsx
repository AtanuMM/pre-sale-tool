import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import {
  applyThemeClass,
  resolveInitialTheme,
  writeStoredTheme,
  type ThemeMode,
} from './themeStorage'
import {
  applyThemeWithTransition,
  type ThemeTransitionOrigin,
} from './viewTransitionTheme'

type ThemeContextValue = {
  theme: ThemeMode
  toggleTheme: (origin?: ThemeTransitionOrigin) => void
  setTheme: (theme: ThemeMode, options?: { origin?: ThemeTransitionOrigin }) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

type ThemeProviderProps = {
  children: ReactNode
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<ThemeMode>(() => resolveInitialTheme())
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    applyThemeClass(theme)
    writeStoredTheme(theme)
  }, [theme])

  const setTheme = useCallback(
    (next: ThemeMode, options?: { origin?: ThemeTransitionOrigin }) => {
      if (!mounted) {
        setThemeState(next)
        return
      }
      applyThemeWithTransition(() => setThemeState(next), options?.origin)
    },
    [mounted],
  )

  const toggleTheme = useCallback(
    (origin?: ThemeTransitionOrigin) => {
      setTheme(theme === 'light' ? 'dark' : 'light', { origin })
    },
    [setTheme, theme],
  )

  const value = useMemo(
    (): ThemeContextValue => ({
      theme,
      toggleTheme,
      setTheme,
    }),
    [theme, toggleTheme, setTheme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) {
    throw new Error('useTheme must be used within ThemeProvider')
  }
  return ctx
}
