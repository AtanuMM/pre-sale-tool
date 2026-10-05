import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardPage } from '@/pages/DashboardPage'
import { PERMISSION_USER_MANAGE } from '@/lib/permissions'
import { createMockAuth, TestAuthProvider } from '@/test/renderWithAuth'
import { ThemeProvider } from '@/theme/ThemeContext'

vi.mock('@/api/users', () => ({
  listUsers: vi.fn().mockResolvedValue({ total: 5, items: [] }),
}))
vi.mock('@/api/roles', () => ({
  listRoles: vi.fn().mockResolvedValue([]),
}))
vi.mock('@/api/settings', () => ({
  getSettings: vi.fn().mockResolvedValue({ allow_self_approval: true }),
}))

import { listUsers } from '@/api/users'

function renderDashboard(permissions: string[]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const auth = createMockAuth({
    user: {
      id: '1',
      email: 'v@example.com',
      full_name: 'Viewer',
      is_active: true,
      permissions,
    },
    hasPermission: (code) => permissions.includes(code),
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <TestAuthProvider auth={auth}>
          <MemoryRouter>
            <DashboardPage />
          </MemoryRouter>
        </TestAuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  )
}

describe('DashboardPage', () => {
  afterEach(() => cleanup())

  it('hides stat cards when user lacks admin permissions', () => {
    renderDashboard(['project.view'])
    expect(screen.queryByText('Total users')).not.toBeInTheDocument()
    expect(listUsers).not.toHaveBeenCalled()
  })

  it('shows user stat when user.manage is granted', async () => {
    renderDashboard([PERMISSION_USER_MANAGE, 'project.view'])
    expect(await screen.findByText('Total users')).toBeInTheDocument()
    expect(listUsers).toHaveBeenCalled()
  })

  it('does not show an Other access group', () => {
    renderDashboard(['input.add', 'project.view'])
    expect(screen.queryByText(/Other/i)).not.toBeInTheDocument()
    expect(screen.getByText(/Intake 1/)).toBeInTheDocument()
  })
})
