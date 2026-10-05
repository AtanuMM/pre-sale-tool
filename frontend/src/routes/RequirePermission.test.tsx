import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { RequirePermission } from './RequirePermission'
import { createMockAuth, TestAuthProvider } from '../test/renderWithAuth'
import { PERMISSION_USER_MANAGE } from '../lib/permissions'

function renderGuard(hasPermission: boolean) {
  const auth = createMockAuth({
    hasPermission: (code: string) => code === PERMISSION_USER_MANAGE && hasPermission,
  })

  render(
    <TestAuthProvider auth={auth}>
      <MemoryRouter initialEntries={['/admin/users']}>
        <Routes>
          <Route element={<RequirePermission permission={PERMISSION_USER_MANAGE} />}>
            <Route path="/admin/users" element={<div>Users content</div>} />
          </Route>
          <Route path="/403" element={<div>Forbidden page</div>} />
        </Routes>
      </MemoryRouter>
    </TestAuthProvider>,
  )
}

describe('RequirePermission', () => {
  it('renders child route when permission is granted', () => {
    renderGuard(true)
    expect(screen.getByText('Users content')).toBeInTheDocument()
  })

  it('redirects to /403 when permission is missing', () => {
    renderGuard(false)
    expect(screen.getByText('Forbidden page')).toBeInTheDocument()
  })
})
