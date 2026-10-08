import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { TestAuthProvider } from '@/test/renderWithAuth'
import { PERMISSION_PROJECT_CREATE } from '@/lib/permissions'
import { NewProjectPage } from './NewProjectPage'

vi.mock('@/api/projects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/projects')>()
  return {
    ...actual,
    getProjectIntakeLimits: vi.fn().mockResolvedValue({
      max_file_bytes: 10_485_760,
      max_files_per_input: 10,
      allowed_extensions: ['txt'],
      max_extracted_chars: 500_000,
    }),
    createProject: vi.fn(),
  }
})

describe('NewProjectPage', () => {
  it('blocks submit without body and files', async () => {
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
              permissions: [PERMISSION_PROJECT_CREATE],
            },
            login: async () => {},
            logout: async () => {},
            hasPermission: (c) => c === PERMISSION_PROJECT_CREATE,
            setUser: () => {},
          }}
        >
            <NewProjectPage />
          </TestAuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await screen.findByLabelText(/Project name/i)
    await user.type(screen.getByLabelText(/Project name/i), 'P')
    await user.type(screen.getByLabelText(/Client name/i), 'C')
    await user.click(screen.getByRole('button', { name: /Create project/i }))
    expect(await screen.findByText(/body or at least one attachment/i)).toBeInTheDocument()
  })
})
