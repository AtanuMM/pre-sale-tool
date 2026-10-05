import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import type { AuthContextValue } from '../auth/AuthContext'
import { AuthContext } from '../auth/AuthContext'
import type { UserPublic } from '../api/types'

const defaultUser: UserPublic = {
  id: 'user-1',
  email: 'viewer@example.com',
  full_name: 'Viewer User',
  is_active: true,
  permissions: [],
}

export function createMockAuth(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  const user = overrides.user !== undefined ? overrides.user : defaultUser
  return {
    status: overrides.status ?? 'authenticated',
    user: overrides.user !== undefined ? overrides.user : user,
    login: overrides.login ?? (async () => {}),
    logout: overrides.logout ?? (async () => {}),
    hasPermission:
      overrides.hasPermission ??
      ((code: string) => (user?.permissions.includes(code) ?? false)),
    setUser: overrides.setUser ?? (() => {}),
  }
}

export function TestAuthProvider({
  auth,
  children,
}: {
  auth?: AuthContextValue
  children: ReactNode
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const value = auth ?? createMockAuth()
  return (
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
    </QueryClientProvider>
  )
}
