import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import * as projectsApi from '@/api/projects'
import { TestAuthProvider } from '@/test/renderWithAuth'
import {
  PERMISSION_PROJECT_CREATE,
  PERMISSION_PROJECT_DELETE,
  PERMISSION_PROJECT_VIEW,
} from '@/lib/permissions'
import { ProjectsListPage } from './ProjectsListPage'

describe('ProjectsListPage', () => {
  it('passes search to listProjects', async () => {
    const listSpy = vi.spyOn(projectsApi, 'listProjects').mockResolvedValue({
      items: [],
      total: 0,
    })
    const user = userEvent.setup()
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <TestAuthProvider
            auth={{
              status: 'authenticated',
              user: {
                id: '1',
                email: 'a@b.com',
                full_name: 'A',
                is_active: true,
                permissions: [PERMISSION_PROJECT_VIEW, PERMISSION_PROJECT_CREATE],
              },
              login: async () => {},
              logout: async () => {},
              hasPermission: (c) =>
                c === PERMISSION_PROJECT_VIEW || c === PERMISSION_PROJECT_CREATE,
              setUser: () => {},
            }}
          >
            <ProjectsListPage />
          </TestAuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await user.type(screen.getByLabelText(/Search projects/i), 'acme')
    await waitFor(() => {
      expect(listSpy).toHaveBeenCalledWith(
        expect.objectContaining({ search: 'acme' }),
      )
    })
  })

  it('confirms before deleting a project', async () => {
    vi.spyOn(projectsApi, 'listProjects').mockResolvedValue({
      items: [
        {
          id: 'p1',
          name: 'Dummy portal',
          client_name: 'Contoso',
          status: 'active',
          created_by_name: 'Admin',
          created_at: '2026-01-01T00:00:00Z',
        },
      ],
      total: 1,
    })
    const deleteSpy = vi.spyOn(projectsApi, 'deleteProject').mockResolvedValue()
    const user = userEvent.setup()
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <TestAuthProvider
            auth={{
              status: 'authenticated',
              user: {
                id: '1',
                email: 'a@b.com',
                full_name: 'A',
                is_active: true,
                permissions: [PERMISSION_PROJECT_VIEW, PERMISSION_PROJECT_DELETE],
              },
              login: async () => {},
              logout: async () => {},
              hasPermission: (c) =>
                c === PERMISSION_PROJECT_VIEW || c === PERMISSION_PROJECT_DELETE,
              setUser: () => {},
            }}
          >
            <ProjectsListPage />
          </TestAuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await user.click(await screen.findByRole('button', { name: /Delete Dummy portal/i }))
    expect(screen.getByText('Delete this project?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('p1')
    })
  })
})
