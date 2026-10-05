import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { UserMenu } from '@/components/layout/UserMenu'
import { createMockAuth, TestAuthProvider } from '@/test/renderWithAuth'
import { ThemeProvider } from '@/theme/ThemeContext'

describe('UserMenu', () => {
  afterEach(() => cleanup())

  it('shows user name and logs out', async () => {
    const logout = vi.fn().mockResolvedValue(undefined)
    const auth = createMockAuth({
      user: {
        id: '1',
        email: 'a@example.com',
        full_name: 'Test User',
        is_active: true,
        permissions: ['user.manage'],
      },
      logout,
    })
    const user = userEvent.setup()
    render(
      <ThemeProvider>
        <TestAuthProvider auth={auth}>
          <UserMenu />
        </TestAuthProvider>
      </ThemeProvider>,
    )
    await user.click(screen.getByRole('button'))
    expect(await screen.findByText('Test User')).toBeInTheDocument()
    await user.click(screen.getByRole('menuitem', { name: /log out/i }))
    expect(logout).toHaveBeenCalled()
  })
})
