import { Outlet, useNavigate } from 'react-router-dom'

import { AuthProvider } from '../auth/AuthContext'

export function Root() {
  const navigate = useNavigate()
  return (
    <AuthProvider onSessionCleared={() => navigate('/login', { replace: true })}>
      <Outlet />
    </AuthProvider>
  )
}
