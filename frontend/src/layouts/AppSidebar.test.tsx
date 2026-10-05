import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { AppSidebar } from '@/components/layout/AppSidebar'
import { SIDEBAR_COLLAPSED_KEY, useSidebarCollapsed } from '@/hooks/useSidebarCollapsed'
import { createMockAuth, TestAuthProvider } from '@/test/renderWithAuth'
import { ThemeProvider } from '@/theme/ThemeContext'
import { PERMISSION_USER_MANAGE } from '@/lib/permissions'

function renderSidebar(permissions: string[]) {
  const auth = createMockAuth({
    user: {
      id: '1',
      email: 'admin@example.com',
      full_name: 'Admin User',
      is_active: true,
      permissions,
    },
    hasPermission: (code: string) => permissions.includes(code),
  })

  return render(
    <ThemeProvider>
      <TestAuthProvider auth={auth}>
        <MemoryRouter>
          <AppSidebar collapsed={false} />
        </MemoryRouter>
      </TestAuthProvider>
    </ThemeProvider>,
  )
}

function CollapseHarness() {
  const { collapsed, toggleCollapsed } = useSidebarCollapsed()
  return (
    <>
      <span>{collapsed ? 'collapsed' : 'expanded'}</span>
      <button type="button" onClick={toggleCollapsed}>
        Toggle sidebar
      </button>
    </>
  )
}

describe('AppSidebar', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => cleanup())

  it('shows only nav items the user has permission for', () => {
    renderSidebar([PERMISSION_USER_MANAGE])
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Users' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Roles' })).not.toBeInTheDocument()
  })
})

describe('useSidebarCollapsed', () => {
  beforeEach(() => localStorage.clear())

  it('persists collapse toggle', async () => {
    const user = userEvent.setup()
    render(
      <ThemeProvider>
        <CollapseHarness />
      </ThemeProvider>,
    )
    expect(screen.getByText('expanded')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Toggle sidebar' }))
    expect(screen.getByText('collapsed')).toBeInTheDocument()
    expect(localStorage.getItem(SIDEBAR_COLLAPSED_KEY)).toBe('true')
  })
})

