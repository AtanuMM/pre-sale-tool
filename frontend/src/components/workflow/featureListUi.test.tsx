import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ProjectStep } from '@/api/steps'
import { GenericStepViewer } from '@/components/workflow/GenericStepViewer'
import { StepPanel } from '@/components/workflow/StepPanel'
import { TooltipProvider } from '@/components/ui/tooltip'
import { pickSelectOption } from '@/test/radixSelect'
import { TestAuthProvider } from '@/test/renderWithAuth'
import { PERMISSION_STEP_GENERATE } from '@/lib/permissions'
import type { StepLayoutSection } from '@/lib/stepLayoutTypes'

vi.mock('@/api/steps', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/steps')>()
  return {
    ...actual,
    getStepVersions: vi.fn().mockResolvedValue([]),
    getStepVersionDetail: vi.fn(),
    generateStep: vi.fn().mockResolvedValue({
      version: {
        id: 'v1',
        version_no: 1,
        status: 'queued',
        source: 'generated',
        created_at: '2026-01-01T00:00:00Z',
        created_by_name: 'A',
        tokens_in: null,
        tokens_out: null,
        error: null,
      },
    }),
    requestStepChanges: vi.fn(),
    approveStepVersion: vi.fn(),
    getStepVersionPrompt: vi.fn(),
    downloadStepVersion: vi.fn(),
  }
})

import { generateStep } from '@/api/steps'
import { ApiError } from '@/api/errors'

const featureLayout: StepLayoutSection[] = [
  { key: 'summary', title: 'Summary', kind: 'text' },
  {
    key: 'stats',
    title: 'Overview',
    kind: 'stats',
    stats_groups: [
      { key: 'by_priority', header: 'Priority' },
      { key: 'by_module', header: 'Module' },
    ],
  },
  { key: 'warnings', title: 'Notes', kind: 'warning_strip' },
  {
    key: 'features',
    title: 'Features',
    kind: 'records',
    record_fields: [
      { key: 'title', header: 'Title' },
      { key: 'description', header: 'Description' },
      { key: 'source_priority', header: 'Source priority' },
    ],
    badge_fields: ['priority', 'origin', 'platforms'],
    id_field: 'id',
    chip_fields: ['source_requirement_ids', 'depends_on_ids', 'linked_gap_refs'],
    group_by: 'module',
    group_source: { section: 'modules', key_field: 'name', intro_field: 'purpose' },
    filter_fields: ['priority', 'platforms'],
  },
]

const featureContent: Record<string, unknown> = {
  summary: 'Portal',
  modules: [
    { name: 'Auth', purpose: 'Sign-in and roles.' },
    { name: 'Orders', purpose: 'Track orders.' },
  ],
  stats: {
    by_priority: { must: 1, should: 1, could: 0, wont: 0 },
    by_module: { Auth: 1, Orders: 1 },
  },
  warnings: [
    { code: 'features_below_source_ratio', count: 3, label: 'Features below 1.5× source requirements' },
  ],
  features: [
    {
      id: 'F-001',
      module: 'Auth',
      title: '<b>Sign in</b>',
      description: 'Users sign in.',
      source_priority: 'Must',
      source_requirement_ids: ['REQ-01'],
      platforms: ['web', 'admin'],
      priority: 'must',
      origin: 'stated',
      depends_on_ids: [],
      linked_gap_refs: ['G-1'],
    },
    {
      id: 'F-002',
      module: 'Orders',
      title: 'Order list',
      description: 'List orders.',
      platforms: ['web'],
      priority: 'should',
      origin: 'implied',
      depends_on_ids: ['F-001'],
      linked_gap_refs: [],
    },
  ],
}

const notesField = {
  key: 'team_notes',
  label: 'Notes and client answers (optional)',
  help_text: 'Paste client answers to the gap questions or decisions made since the intake. Used only for this step.',
  kind: 'textarea' as const,
  max_length: 8000,
}

function featureStep(overrides: Partial<ProjectStep> = {}): ProjectStep {
  return {
    key: 'feature_list',
    title: 'Feature List',
    order: 3,
    implemented: true,
    status: 'ready',
    has_failed_attempt: false,
    can_generate: true,
    blocked_reason: null,
    current_version_id: null,
    can_request_changes: false,
    can_approve: false,
    approve_blocked_reason: null,
    latest_version: null,
    layout: featureLayout,
    reads_description: 'Reads scope and gap.',
    writes_description: 'Writes features.',
    context_steps: [
      { key: 'scope_analysis', title: 'Scope Analysis' },
      { key: 'gap_analysis', title: 'Gap Analysis' },
    ],
    input_fields: [notesField],
    ...overrides,
  }
}

function renderPanel(step: ProjectStep, permissions: string[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
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
            hasPermission: (c) => permissions.includes(c),
            setUser: () => {},
          }}
        >
          <StepPanel
            projectId="p1"
            step={step}
            initialInput={undefined}
            hasPermission={(c) => permissions.includes(c)}
          />
        </TestAuthProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.mocked(generateStep).mockClear()
})

describe('Feature list viewer', () => {
  it('groups by module, shows text badges, ref chips and literal HTML', () => {
    render(<GenericStepViewer layout={featureLayout} content={featureContent} />)
    expect(screen.getByText('Auth')).toBeInTheDocument()
    expect(screen.getByText('Sign-in and roles.')).toBeInTheDocument()
    expect(screen.getByText('Orders')).toBeInTheDocument()
    expect(screen.getByText('<b>Sign in</b>')).toBeInTheDocument()
    expect(screen.getByText(/Priority: Must/i)).toBeInTheDocument()
    expect(screen.getByText(/Origin: Stated/i)).toBeInTheDocument()
    expect(screen.getByText(/Platforms: Web, Admin/i)).toBeInTheDocument()
    expect(screen.getAllByText('F-001').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('G-1')).toBeInTheDocument()
    expect(screen.getByText('F-002')).toBeInTheDocument()
    expect(screen.getByText(/Must 1/)).toBeInTheDocument()
    expect(screen.getByText('REQ-01')).toBeInTheDocument()
    expect(screen.getByText('Source priority')).toBeInTheDocument()
    expect(screen.getAllByText('Must').length).toBeGreaterThan(0)
    expect(screen.getByText(/Features below 1.5× source requirements: 3/)).toBeInTheDocument()
  })

  it('filters by priority', async () => {
    const user = userEvent.setup()
    render(<GenericStepViewer layout={featureLayout} content={featureContent} />)
    const priority = screen.getByLabelText('Priority')
    await pickSelectOption(user, priority, 'must')
    expect(screen.getByText('<b>Sign in</b>')).toBeInTheDocument()
    expect(screen.queryByText('Order list')).not.toBeInTheDocument()
    expect(screen.getByText(/Showing 1 of 2/)).toBeInTheDocument()
  })

  it('shows assumption ref chips on a list section', () => {
    render(
      <GenericStepViewer
        layout={[{ key: 'assumptions', title: 'Assumptions', kind: 'list', ref_prefix: 'A' }]}
        content={{ assumptions: ['API docs exist'] }}
      />,
    )
    expect(screen.getByText('A-1')).toBeInTheDocument()
    expect(screen.getByText('API docs exist')).toBeInTheDocument()
  })
})

describe('Feature list ready and locked', () => {
  it('shows locked blocked_reason', () => {
    renderPanel(
      featureStep({
        status: 'locked',
        can_generate: false,
        blocked_reason: 'Previous step must be approved before generating this step',
      }),
      [PERMISSION_STEP_GENERATE],
    )
    expect(
      screen.getByText('Previous step must be approved before generating this step'),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText(/notes and client answers/i)).not.toBeInTheDocument()
  })

  it('ready state shows notes box and context steps', () => {
    renderPanel(featureStep(), [PERMISSION_STEP_GENERATE])
    expect(screen.getByLabelText(/notes and client answers/i)).toBeInTheDocument()
    expect(screen.getByText('Scope Analysis')).toBeInTheDocument()
    expect(screen.getByText('Gap Analysis')).toBeInTheDocument()
    expect(screen.getByText(/0 \/ 8000 characters/)).toBeInTheDocument()
  })

  it('keeps notes text when generate fails and sends stripped text', async () => {
    const user = userEvent.setup()
    vi.mocked(generateStep).mockRejectedValueOnce(new ApiError(409, 'Conflict'))
    renderPanel(featureStep(), [PERMISSION_STEP_GENERATE])
    const area = screen.getByLabelText(/notes and client answers/i)
    await user.type(area, '  client said okta  ')
    await user.click(screen.getByRole('button', { name: 'Generate' }))
    await waitFor(() => {
      expect(generateStep).toHaveBeenCalledWith('p1', 'feature_list', {
        team_notes: 'client said okta',
      })
    })
    expect(area).toHaveValue('  client said okta  ')
  })
})
