import { Navigate, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'

type RequirePermissionProps = {
  permission: string
}

export function RequirePermission({ permission }: RequirePermissionProps) {
  const { hasPermission } = useAuth()

  if (!hasPermission(permission)) {
    return <Navigate to="/403" replace />
  }

  return <Outlet />
}
