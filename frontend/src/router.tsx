import { createBrowserRouter } from 'react-router-dom'

import { AppLayout } from '@/layouts/AppLayout'
import { DashboardPage } from '@/pages/DashboardPage'
import { ForbiddenPage } from '@/pages/ForbiddenPage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { RolesPage } from '@/pages/admin/RolesPage'
import { SettingsPage } from '@/pages/admin/SettingsPage'
import { UsersPage } from '@/pages/admin/UsersPage'
import { GuestRoute } from '@/routes/GuestRoute'
import { ProtectedRoute } from '@/routes/ProtectedRoute'
import { RequirePermission } from '@/routes/RequirePermission'
import { Root } from '@/routes/Root'
import { NewProjectPage } from '@/pages/projects/NewProjectPage'
import { ProjectDetailPage } from '@/pages/projects/ProjectDetailPage'
import { ProjectsListPage } from '@/pages/projects/ProjectsListPage'
import {
  PERMISSION_PROJECT_CREATE,
  PERMISSION_PROJECT_VIEW,
  PERMISSION_ROLE_MANAGE,
  PERMISSION_SETTINGS_MANAGE,
  PERMISSION_USER_MANAGE,
} from '@/lib/permissions'

export const router = createBrowserRouter([
  {
    element: <Root />,
    children: [
      {
        element: <GuestRoute />,
        children: [{ path: '/login', element: <LoginPage /> }],
      },
      {
        element: <ProtectedRoute />,
        children: [
          {
            element: <AppLayout />,
            children: [
              { index: true, element: <DashboardPage /> },
              {
                path: 'projects',
                element: <RequirePermission permission={PERMISSION_PROJECT_VIEW} />,
                children: [
                  { index: true, element: <ProjectsListPage /> },
                  {
                    path: 'new',
                    element: <RequirePermission permission={PERMISSION_PROJECT_CREATE} />,
                    children: [{ index: true, element: <NewProjectPage /> }],
                  },
                  { path: ':projectId', element: <ProjectDetailPage /> },
                ],
              },
              { path: '403', element: <ForbiddenPage /> },
              {
                path: 'admin/users',
                element: <RequirePermission permission={PERMISSION_USER_MANAGE} />,
                children: [{ index: true, element: <UsersPage /> }],
              },
              {
                path: 'admin/roles',
                element: <RequirePermission permission={PERMISSION_ROLE_MANAGE} />,
                children: [{ index: true, element: <RolesPage /> }],
              },
              {
                path: 'admin/settings',
                element: <RequirePermission permission={PERMISSION_SETTINGS_MANAGE} />,
                children: [{ index: true, element: <SettingsPage /> }],
              },
            ],
          },
        ],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
