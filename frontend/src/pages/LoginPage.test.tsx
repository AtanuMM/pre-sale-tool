import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: { error: vi.fn() },
}))

import { ApiError } from '../api/errors'
import { LoginPage } from './LoginPage'
import { createMockAuth, TestAuthProvider } from '../test/renderWithAuth'
import { ThemeProvider } from '@/theme/ThemeContext'
import { TooltipProvider } from '@/components/ui/tooltip'

describe('LoginPage', () => {
  it('shows backend error message on failed login', async () => {
    const login = vi.fn().mockRejectedValue(new ApiError(401, 'Invalid email or password'))
    const auth = createMockAuth({
      status: 'anonymous',
      user: null,
      login,
    })

    render(
      <ThemeProvider>
        <TooltipProvider>
          <TestAuthProvider auth={auth}>
            <MemoryRouter>
              <LoginPage />
            </MemoryRouter>
          </TestAuthProvider>
        </TooltipProvider>
      </ThemeProvider>,
    )

    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'wrong@example.com')
    await user.type(screen.getByLabelText('Password'), 'bad-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    const { toast } = await import('sonner')
    expect(toast.error).toHaveBeenCalledWith('Invalid email or password')
  })
})
