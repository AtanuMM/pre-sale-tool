import { render, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as client from '../api/client'
import { ProtectedRoute } from './ProtectedRoute'
import { Root } from './Root'

describe('Root session handling', () => {
  beforeEach(() => {
    client.resetClientAuthState()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sends unauthenticated users on protected routes to /login after bootstrap', async () => {
    vi.spyOn(client, 'bootstrapRefresh').mockResolvedValue(null)

    const router = createMemoryRouter(
      [
        {
          element: <Root />,
          children: [
            { path: '/login', element: <div>Login screen</div> },
            {
              element: <ProtectedRoute />,
              children: [{ path: '/', element: <div>Home screen</div> }],
            },
          ],
        },
      ],
      { initialEntries: ['/'] },
    )

    render(<RouterProvider router={router} />)

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/login')
    })
  })
})
