import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { PlainTextBlock } from '@/components/projects/PlainTextBlock'
import { TooltipProvider } from '@/components/ui/tooltip'
import { TestAuthProvider } from '@/test/renderWithAuth'
import { PERMISSION_INPUT_ADD, PERMISSION_PROJECT_ARCHIVE } from '@/lib/permissions'
import { ProjectDetailPage } from './ProjectDetailPage'

vi.mock('@/api/projects', () => ({
  getProjectOverview: vi.fn().mockResolvedValue({
    project: {
      id: 'p1',
      name: 'Test',
      client_name: 'Co',
      status: 'archived',
      allow_self_approval: null,
      created_by_name: 'Admin',
      created_at: '2026-01-01T00:00:00Z',
      completed_at: null,
    },
    effective_allow_self_approval: true,
    inputs: [
      {
        id: 'i1',
        kind: 'email',
        received_at: '2026-01-01T00:00:00Z',
        received_from: null,
        subject: null,
        body: '<b>not html</b>',
        is_followup: false,
        created_by_name: 'Admin',
        created_at: '2026-01-01T00:00:00Z',
        files: [],
      },
    ],
    timeline: [{ action: 'unknown.custom.action', actor_name: 'x', occurred_at: '2026-01-01T00:00:00Z' }],
  }),
  getProjectIntakeLimits: vi.fn().mockResolvedValue({
    max_file_bytes: 10_485_760,
    max_files_per_input: 10,
    allowed_extensions: ['txt'],
    max_extracted_chars: 500_000,
  }),
  archiveProject: vi.fn(),
  restoreProject: vi.fn(),
  patchProjectSettings: vi.fn(),
  createFollowUpInput: vi.fn(),
  downloadProjectFile: vi.fn(),
  getProjectFileText: vi.fn(),
}))

describe('PlainTextBlock', () => {
  it('renders HTML tags literally', () => {
    render(<PlainTextBlock text="<script>alert(1)</script>" />)
    expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument()
  })
})

function renderDetailPage(
  permissions: string[],
  hasPermission: (c: string) => boolean,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={['/projects/p1']}>
          <TestAuthProvider
            auth={{
              status: 'authenticated',
              user: {
                id: '1',
                email: 'a@b.com',
                full_name: 'A',
                is_active: true,
                permissions,
              },
              login: async () => {},
              logout: async () => {},
              hasPermission,
              setUser: () => {},
            }}
          >
            <Routes>
              <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
            </Routes>
          </TestAuthProvider>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

describe('ProjectDetailPage', () => {
  it('disables follow-up on archived project', async () => {
    renderDetailPage(
      [PERMISSION_INPUT_ADD, PERMISSION_PROJECT_ARCHIVE],
      (c) => c === PERMISSION_INPUT_ADD || c === PERMISSION_PROJECT_ARCHIVE,
    )
    expect(await screen.findByRole('button', { name: /Add follow-up/i })).toBeDisabled()
  })

  it('settings select disabled without settings.manage', async () => {
    const user = userEvent.setup()
    renderDetailPage([], () => false)
    await screen.findByRole('heading', { name: 'Test' })
    await user.click(screen.getByRole('button', { name: 'Settings' }))
    expect(screen.getByLabelText(/Override/i)).toBeDisabled()
  })
})
