import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ProjectStep } from '@/api/steps'
import { GenericStepViewer } from '@/components/workflow/GenericStepViewer'
import { StepPanel } from '@/components/workflow/StepPanel'
import {
  RequestChangesSheet,
  validateRequestChangesText,
} from '@/components/workflow/RequestChangesSheet'
import { WorkflowStepStatusBadge } from '@/components/workflow/WorkflowStepStatusBadge'
import { TooltipProvider } from '@/components/ui/tooltip'
import { TestAuthProvider } from '@/test/renderWithAuth'
import {
  PERMISSION_DOCUMENT_DOWNLOAD,
  PERMISSION_STEP_APPROVE,
  PERMISSION_STEP_GENERATE,
  PERMISSION_STEP_REQUEST_CHANGES,
} from '@/lib/permissions'
import type { StepLayoutSection } from '@/lib/stepLayoutTypes'

vi.mock('@/api/steps', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/steps')>()
  return {
    ...actual,
    getStepVersions: vi.fn().mockResolvedValue([]),
    getStepVersionDetail: vi.fn(),
    generateStep: vi.fn(),
    requestStepChanges: vi.fn(),
    approveStepVersion: vi.fn(),
    getStepVersionPrompt: vi.fn(),
    downloadStepVersionDocx: vi.fn(),
  }
})

import {
  approveStepVersion,
  downloadStepVersionDocx,
  getStepVersionDetail,
  getStepVersions,
  requestStepChanges,
} from '@/api/steps'
import { triggerBrowserDownload } from '@/api/download'
import { ApiError } from '@/api/errors'

const scopeLayout: StepLayoutSection[] = [
  { key: 'executive_summary', title: 'Executive summary', kind: 'text' },
  { key: 'objectives', title: 'Objectives', kind: 'list' },
  {
    key: 'ambiguities_and_questions',
    title: 'Ambiguities and questions',
    kind: 'table',
    columns: [
      { key: 'question', header: 'Question' },
      { key: 'why_it_matters', header: 'Why it matters' },
    ],
    copyable: true,
  },
  { key: 'in_scope', title: 'In scope', kind: 'list' },
]

const sampleContent: Record<string, unknown> = {
  executive_summary: 'Summary',
  objectives: ['A'],
  ambiguities_and_questions: [
    { question: '<b>Q1</b>', why_it_matters: 'Because' },
  ],
  in_scope: ['Portal'],
}

function baseStep(overrides: Partial<ProjectStep>): ProjectStep {
  return {
    key: 'scope_analysis',
    title: 'Scope analysis',
    order: 1,
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
    layout: scopeLayout,
    reads_description: 'Reads intake.',
    writes_description: 'Writes scope.',
    context_steps: [],
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

const detailInReview = {
  id: 'v1',
  project_id: 'p1',
  step_key: 'scope_analysis',
  version_no: 1,
  status: 'in_review' as const,
  source: 'generated' as const,
  content: sampleContent,
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
}

vi.mock('@/api/download', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/download')>()
  return {
    ...actual,
    triggerBrowserDownload: vi.fn(),
  }
})

afterEach(() => {
  cleanup()
})

describe('WorkflowStepStatusBadge', () => {
  it('shows failed attempt label', () => {
    render(
      <WorkflowStepStatusBadge status="in_review" hasFailedAttempt />,
    )
    expect(screen.getByText('In review')).toBeInTheDocument()
    expect(screen.getByText('Failed attempt')).toBeInTheDocument()
  })

  it('shows Coming soon when step is not implemented', () => {
    render(
      <WorkflowStepStatusBadge status="ready" implemented={false} />,
    )
    expect(screen.getByText('Coming soon')).toBeInTheDocument()
    expect(screen.queryByText('Ready')).not.toBeInTheDocument()
  })
})

describe('validateRequestChangesText', () => {
  it('rejects empty and whitespace', () => {
    expect(validateRequestChangesText('')).toMatch(/empty/)
    expect(validateRequestChangesText('   ')).toMatch(/empty/)
  })

  it('rejects over 4000', () => {
    expect(validateRequestChangesText('a'.repeat(4001))).toMatch(/4000/)
  })
})

describe('RequestChangesSheet', () => {
  it('submits stripped text via callback', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    function Wrapper() {
      const [text, setText] = useState('  hello  ')
      return (
        <RequestChangesSheet
          open
          onOpenChange={() => {}}
          text={text}
          onTextChange={setText}
          error={null}
          onSubmit={onSubmit}
          submitting={false}
        />
      )
    }
    render(<Wrapper />)
    await user.click(screen.getByRole('button', { name: /submit revision/i }))
    expect(onSubmit).toHaveBeenCalled()
  })
})

describe('GenericStepViewer', () => {
  it('renders HTML in questions literally', () => {
    render(<GenericStepViewer layout={scopeLayout} content={sampleContent} />)
    expect(screen.getByText('<b>Q1</b>')).toBeInTheDocument()
  })

  it('shows severity badges with text for gap records', () => {
    const gapLayout: StepLayoutSection[] = [
      {
        key: 'gaps',
        title: 'Gaps',
        kind: 'records',
        badge_fields: ['severity', 'category'],
        record_fields: [{ key: 'title', header: 'Title' }],
      },
    ]
    render(
      <GenericStepViewer
        layout={gapLayout}
        content={{
          gaps: [
            { title: 'Auth', severity: 'high', category: 'ambiguity' },
          ],
        }}
      />,
    )
    expect(screen.getByText(/Severity: High/i)).toBeInTheDocument()
    expect(screen.getByText(/Category: Ambiguity/i)).toBeInTheDocument()
  })
})

describe('StepPanel', () => {
  beforeEach(() => {
    vi.mocked(getStepVersionDetail).mockReset()
  })

  it('hides Generate without permission', () => {
    renderPanel(baseStep({ status: 'ready', can_generate: true }), [])
    expect(screen.queryByRole('button', { name: 'Generate' })).not.toBeInTheDocument()
  })

  it('shows blocked_reason when generate disabled', () => {
    renderPanel(
      baseStep({
        status: 'ready',
        can_generate: false,
        blocked_reason: 'No readable content',
      }),
      [PERMISSION_STEP_GENERATE],
    )
    expect(screen.getByText('No readable content')).toBeInTheDocument()
  })

  it('shows approve_blocked_reason beside disabled approve', async () => {
    vi.mocked(getStepVersionDetail).mockResolvedValue(detailInReview)
    renderPanel(
      baseStep({
        status: 'in_review',
        current_version_id: 'v1',
        can_approve: false,
        approve_blocked_reason: 'Self-approval is not allowed for this project',
        can_request_changes: true,
      }),
      [PERMISSION_STEP_APPROVE, PERMISSION_STEP_REQUEST_CHANGES],
    )
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
    })
    expect(
      screen.getByText('Self-approval is not allowed for this project'),
    ).toBeInTheDocument()
  })

  it('shows failed revision notice', async () => {
    vi.mocked(getStepVersionDetail).mockResolvedValue(detailInReview)
    renderPanel(
      baseStep({
        status: 'in_review',
        has_failed_attempt: true,
        current_version_id: 'v1',
      }),
      [],
    )
    await waitFor(() => {
      expect(
        screen.getByText(/last revision failed/i),
      ).toBeInTheDocument()
    })
  })

  it('hides download without document.download permission', async () => {
    vi.mocked(getStepVersionDetail).mockResolvedValue(detailInReview)
    renderPanel(
      baseStep({
        status: 'in_review',
        current_version_id: 'v1',
      }),
      [],
    )
    await waitFor(() => {
      expect(screen.getByText('Summary')).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('button', { name: /download draft/i }),
    ).not.toBeInTheDocument()
  })

  it('downloads via authenticated blob helper with draft label', async () => {
    vi.mocked(getStepVersionDetail).mockResolvedValue(detailInReview)
    vi.mocked(getStepVersions).mockResolvedValue([
      {
        id: 'v1',
        version_no: 1,
        status: 'in_review',
        source: 'generated',
        created_at: detailInReview.created_at,
        created_by_name: 'A',
        tokens_in: null,
        tokens_out: null,
        error: null,
      },
    ])
    vi.mocked(downloadStepVersionDocx).mockResolvedValue({
      blob: new Blob(['x']),
      filename: 'draft.docx',
    })
    const user = userEvent.setup()
    renderPanel(
      baseStep({
        status: 'in_review',
        current_version_id: 'v1',
      }),
      [PERMISSION_DOCUMENT_DOWNLOAD],
    )
    const btn = await screen.findByRole('button', { name: /download draft/i })
    await user.click(btn)
    await waitFor(() => {
      expect(downloadStepVersionDocx).toHaveBeenCalledWith('v1', 'scope_analysis-v1.docx')
    })
    expect(triggerBrowserDownload).toHaveBeenCalled()
  })

  it('refetches on 409 approve', async () => {
    vi.mocked(getStepVersionDetail).mockResolvedValue(detailInReview)
    vi.mocked(approveStepVersion).mockRejectedValue(
      new ApiError(409, 'Version is not current'),
    )
    const user = userEvent.setup()
    renderPanel(
      baseStep({
        status: 'in_review',
        current_version_id: 'v1',
        can_approve: true,
        can_request_changes: false,
      }),
      [PERMISSION_STEP_APPROVE],
    )
    const actionApprove = await screen.findByRole('button', { name: /^Approve$/i })
    await user.click(actionApprove)
    const dialog = await screen.findByRole('dialog', { name: /approve this version/i })
    await user.click(within(dialog).getByRole('button', { name: /^Approve$/i }))
    await waitFor(() => {
      expect(approveStepVersion).toHaveBeenCalled()
    })
  })
})

describe('requestStepChanges on 409', () => {
  afterEach(() => vi.clearAllMocks())

  it('keeps sheet text on failure', async () => {
    vi.mocked(getStepVersionDetail).mockResolvedValue(detailInReview)
    vi.mocked(requestStepChanges).mockRejectedValue(new ApiError(409, 'Conflict'))
    const user = userEvent.setup()
    renderPanel(
      baseStep({
        status: 'in_review',
        current_version_id: 'v1',
        can_request_changes: true,
      }),
      [PERMISSION_STEP_REQUEST_CHANGES],
    )
    const reqBtn = await screen.findByRole('button', { name: 'Request changes' })
    await user.click(reqBtn)
    const area = screen.getByLabelText(/instructions/i)
    await user.type(area, 'Please fix scope')
    await user.click(screen.getByRole('button', { name: /submit revision/i }))
    await waitFor(() => expect(requestStepChanges).toHaveBeenCalled())
    expect(area).toHaveValue('Please fix scope')
  })
})
