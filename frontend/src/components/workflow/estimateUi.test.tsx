import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ProjectStep } from '@/api/steps'
import { GenericStepViewer } from '@/components/workflow/GenericStepViewer'
import { StepInputFields } from '@/components/workflow/StepInputFields'
import { StepPanel } from '@/components/workflow/StepPanel'
import { TooltipProvider } from '@/components/ui/tooltip'
import { TestAuthProvider } from '@/test/renderWithAuth'
import {
  PERMISSION_DOCUMENT_DOWNLOAD,
  PERMISSION_STEP_GENERATE,
  PERMISSION_STEP_REQUEST_CHANGES,
} from '@/lib/permissions'
import type { StepInputField, StepInputValue, StepLayoutSection } from '@/lib/stepLayoutTypes'
import { defaultInputValues } from '@/lib/stepInputValues'

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

import { downloadStepVersion, generateStep, getStepVersionDetail, getStepVersions } from '@/api/steps'

const teamField: StepInputField = {
  key: 'team',
  label: 'Team',
  help_text: 'Roles that will deliver this work.',
  kind: 'table',
  max_length: 8000,
  required: true,
  min_rows: 1,
  max_rows: 15,
  unique_column: 'role',
  require_estimated_row: true,
  columns: [
    { key: 'role', label: 'Role', kind: 'text' },
    {
      key: 'mode',
      label: 'Mode',
      kind: 'select',
      options: ['estimated', 'percent_of_delivery', 'duration_based'],
      default: 'estimated',
    },
    { key: 'headcount', label: 'Headcount', kind: 'number', default: 1, step: 0.5 },
    { key: 'ai_gain_pct', label: 'AI gain %', kind: 'number', default: 0 },
  ],
}

const estimateLayout: StepLayoutSection[] = [
  { key: 'cards', title: 'Summary', kind: 'computed_cards', source: 'computed.cards' },
  { key: 'warnings', title: 'Notes', kind: 'warning_strip', source: 'computed.warnings' },
  {
    key: 'feature_rows',
    title: 'Features',
    kind: 'computed_table',
    source: 'computed.feature_rows',
    columns: [
      { key: 'id', header: 'ID' },
      { key: 'title', header: 'Title' },
      { key: 'phase', header: 'Phase' },
      { key: 'component', header: 'Component' },
    ],
    filter_fields: ['phase', 'component'],
  },
]

const estimateContent: Record<string, unknown> = {
  summary: 'Dummy',
  computed: {
    cards: [
      { key: 'hours_with_ai', label: 'Hours with AI tools', value: '88 h' },
      { key: 'saving_pct', label: 'AI saving', value: '12%' },
    ],
    warnings: [{ code: 'features_not_estimated', count: 1, label: 'Features not estimated' }],
    feature_rows: [
      { id: 'F-001', title: '<b>Sign in</b>', phase: 'mvp', component: 'API' },
      { id: 'F-002', title: 'Orders', phase: 'phase_1', component: 'Web' },
    ],
  },
}

function estimateStep(overrides: Partial<ProjectStep> = {}): ProjectStep {
  return {
    key: 'estimate',
    title: 'Estimate',
    order: 4,
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
    layout: estimateLayout,
    reads_description: 'Reads feature list.',
    writes_description: 'Writes estimate.',
    context_steps: [{ key: 'feature_list', title: 'Feature List' }],
    input_fields: [teamField],
    export_formats: ['docx', 'xlsx', 'csv'],
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

describe('Estimate form', () => {
  it('fills typical team example rows', async () => {
    const user = userEvent.setup()
    function Harness() {
      const [values, setValues] = useState<Record<string, StepInputValue>>(
        defaultInputValues([teamField]),
      )
      return (
        <StepInputFields
          fields={[teamField]}
          values={values}
          onChange={(key, value) => setValues((prev) => ({ ...prev, [key]: value }))}
        />
      )
    }
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: /use a typical team/i }))
    expect(screen.getByDisplayValue('Developer')).toBeInTheDocument()
    expect(screen.getByText(/examples, not recommendations/i)).toBeInTheDocument()
    expect(screen.getByText(/Headcount total: 8/)).toBeInTheDocument()
  })

  it('warns when AI gain is above 50', async () => {
    const user = userEvent.setup()
    function Harness() {
      const [values, setValues] = useState<Record<string, StepInputValue>>(
        defaultInputValues([teamField]),
      )
      return (
        <StepInputFields
          fields={[teamField]}
          values={values}
          onChange={(key, value) => setValues((prev) => ({ ...prev, [key]: value }))}
        />
      )
    }
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: /add row/i }))
    const gain = screen.getByLabelText('AI gain % row 1')
    await user.clear(gain)
    await user.type(gain, '60')
    expect(screen.getByText(/AI gain above 50%/i)).toBeInTheDocument()
  })
})

describe('Estimate viewer', () => {
  it('shows cards, warning strip, filters and literal HTML', async () => {
    const user = userEvent.setup()
    render(<GenericStepViewer layout={estimateLayout} content={estimateContent} />)
    expect(screen.getByText('Hours with AI tools')).toBeInTheDocument()
    expect(screen.getByText('88 h')).toBeInTheDocument()
    expect(screen.getByText(/Features not estimated: 1/)).toBeInTheDocument()
    expect(screen.getByText('<b>Sign in</b>')).toBeInTheDocument()
    const phase = screen.getByLabelText('Phase')
    await user.selectOptions(phase, 'mvp')
    expect(screen.getByText('<b>Sign in</b>')).toBeInTheDocument()
    expect(screen.queryByText('Orders')).not.toBeInTheDocument()
  })
})

describe('Estimate panel', () => {
  it('shows locked blocked_reason', () => {
    renderPanel(
      estimateStep({
        status: 'locked',
        can_generate: false,
        blocked_reason: 'Previous step must be approved before generating this step',
      }),
      [PERMISSION_STEP_GENERATE],
    )
    expect(
      screen.getByText('Previous step must be approved before generating this step'),
    ).toBeInTheDocument()
  })

  it('download menu lists excel and csv', async () => {
    vi.mocked(getStepVersionDetail).mockResolvedValue({
      id: 'v1',
      project_id: 'p1',
      step_key: 'estimate',
      version_no: 1,
      status: 'in_review',
      source: 'generated',
      content: estimateContent,
      inputs: {},
      based_on_version_id: null,
      instructions: null,
      error: null,
      model_id: null,
      prompt_version: null,
      tokens_in: null,
      tokens_out: null,
      created_at: '2026-01-01T00:00:00Z',
      created_by_name: 'A',
      generation_started_at: null,
      generation_finished_at: null,
      approval: null,
    })
    vi.mocked(getStepVersions).mockResolvedValue([
      {
        id: 'v1',
        version_no: 1,
        status: 'in_review',
        source: 'generated',
        created_at: '2026-01-01T00:00:00Z',
        created_by_name: 'A',
        tokens_in: null,
        tokens_out: null,
        error: null,
      },
    ])
    vi.mocked(downloadStepVersion).mockResolvedValue({
      blob: new Blob(['x']),
      filename: 'draft.xlsx',
    })
    const user = userEvent.setup()
    renderPanel(
      estimateStep({
        status: 'in_review',
        current_version_id: 'v1',
        can_request_changes: true,
      }),
      [PERMISSION_DOCUMENT_DOWNLOAD, PERMISSION_STEP_REQUEST_CHANGES],
    )
    await user.click(await screen.findByRole('button', { name: /^download$/i }))
    expect(screen.getByText(/Excel/i)).toBeInTheDocument()
    expect(screen.getByText(/CSV/i)).toBeInTheDocument()
    await user.click(screen.getByText(/Excel/i))
    await waitFor(() => {
      expect(downloadStepVersion).toHaveBeenCalledWith('v1', 'xlsx', 'estimate-v1.xlsx')
    })
  })

  it('shows estimating batch progress', () => {
    vi.mocked(getStepVersionDetail).mockResolvedValue({
      id: 'v9',
      project_id: 'p1',
      step_key: 'estimate',
      version_no: 1,
      status: 'generating',
      source: 'generated',
      content: null,
      inputs: { generation_progress: { done: 2, total: 4 } },
      based_on_version_id: null,
      instructions: null,
      error: null,
      model_id: null,
      prompt_version: null,
      tokens_in: null,
      tokens_out: null,
      created_at: '2026-01-01T00:00:00Z',
      created_by_name: 'A',
      generation_started_at: '2026-01-01T00:00:00Z',
      generation_finished_at: null,
      approval: null,
    })
    renderPanel(
      estimateStep({
        status: 'generating',
        latest_version: {
          id: 'v9',
          version_no: 1,
          status: 'generating',
          source: 'generated',
          created_at: '2026-01-01T00:00:00Z',
          created_by_name: 'A',
          tokens_in: null,
          tokens_out: null,
          error: null,
        },
        generation_progress: { done: 2, total: 4 },
      }),
      [PERMISSION_STEP_GENERATE],
    )
    expect(screen.getByText(/Estimating batch 2 of 4/i)).toBeInTheDocument()
  })
})

describe('Estimate v2 form', () => {
  const v2Team: StepInputField = {
    ...teamField,
    columns: [
      { key: 'role', label: 'Role', kind: 'text' },
      {
        key: 'discipline',
        label: 'Discipline',
        kind: 'select',
        options: ['development', 'qa', 'other'],
        default: 'other',
      },
      {
        key: 'ai_gain_pct',
        label: 'AI gain %',
        kind: 'number',
        default: 0,
        enabled_when: { column: 'discipline', value: 'development' },
      },
    ],
  }

  it('disables AI gain unless discipline is development', async () => {
    const user = userEvent.setup()
    function Harness() {
      const [values, setValues] = useState<Record<string, StepInputValue>>(
        defaultInputValues([v2Team]),
      )
      return (
        <StepInputFields
          fields={[v2Team]}
          values={values}
          onChange={(key, value) => setValues((prev) => ({ ...prev, [key]: value }))}
        />
      )
    }
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: /add row/i }))
    const gain = screen.getByLabelText('AI gain % row 1')
    expect(gain).toBeDisabled()
    expect(screen.getByText(/AI gain applies only to development roles/i)).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Discipline row 1'), 'development')
    expect(screen.getByLabelText('AI gain % row 1')).not.toBeDisabled()
  })
})

describe('Estimate health', () => {
  it('renders health rows first', () => {
    render(
      <GenericStepViewer
        layout={[
          {
            key: 'health_rows',
            title: 'Estimate health',
            kind: 'computed_table',
            source: 'computed.health_rows',
            columns: [
              { key: 'check', header: 'Check' },
              { key: 'value', header: 'Value' },
              { key: 'status', header: 'Status' },
            ],
          },
        ]}
        content={{
          computed: {
            health_rows: [
              { check: 'Project AI cap', value: 'factor 0.83', threshold: '25%', status: 'warn' },
            ],
          },
        }}
      />,
    )
    expect(screen.getAllByText('Estimate health').length).toBeGreaterThan(0)
    expect(screen.getByText('Project AI cap')).toBeInTheDocument()
    expect(screen.getByText('warn')).toBeInTheDocument()
  })
})
