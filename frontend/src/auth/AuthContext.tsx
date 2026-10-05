import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { login as apiLogin } from '../api/auth'
import {
  bootstrapRefresh,
  logoutRequest,
  setSessionHandlers,
} from '../api/client'
import type { UserPublic } from '../api/types'
import { hasPermission as checkPermission } from '../lib/permissions'

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

export type AuthContextValue = {
  status: AuthStatus
  user: UserPublic | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  hasPermission: (code: string) => boolean
  setUser: (user: UserPublic | null) => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

type AuthProviderProps = {
  children: ReactNode
  onSessionCleared?: () => void
}

export function AuthProvider({ children, onSessionCleared }: AuthProviderProps) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<UserPublic | null>(null)

  useEffect(() => {
    setSessionHandlers({
      onSessionCleared: () => {
        setUser(null)
        setStatus('anonymous')
        onSessionCleared?.()
      },
    })
    return () => setSessionHandlers({})
  }, [onSessionCleared])

  useEffect(() => {
    let cancelled = false
    void bootstrapRefresh().then((data) => {
      if (cancelled) return
      if (data) {
        setUser(data.user)
        setStatus('authenticated')
      } else {
        setUser(null)
        setStatus('anonymous')
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const data = await apiLogin({ email, password })
    setUser(data.user)
    setStatus('authenticated')
  }, [])

  const logout = useCallback(async () => {
    await logoutRequest()
    setUser(null)
    setStatus('anonymous')
  }, [])

  const hasPermission = useCallback(
    (code: string) => {
      if (!user) return false
      return checkPermission(user.permissions, code)
    },
    [user],
  )

  const value = useMemo(
    (): AuthContextValue => ({
      status,
      user,
      login,
      logout,
      hasPermission,
      setUser,
    }),
    [status, user, login, logout, hasPermission],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}
