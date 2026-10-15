import type {
  StepContextStep,
  StepInputField,
  StepLayoutSection,
} from '@/lib/stepLayoutTypes'

import { apiFetchBlob } from './download'
import { apiRequest } from './client'

export type DerivedStepStatus =
  | 'locked'
  | 'ready'
  | 'generating'
  | 'in_review'
  | 'approved'
  | 'stale'

export type StepVersionStatus =
  | 'queued'
  | 'generating'
  | 'in_review'
  | 'approved'
  | 'failed'
  | 'changes_requested'
  | 'superseded'
  | 'stale'

export type StepVersionSource = 'generated' | 'manual_edit' | 'section_regen'

export type StepVersionSummary = {
  id: string
  version_no: number
  status: StepVersionStatus
  source: StepVersionSource
  created_at: string
  created_by_name: string | null
  tokens_in: number | null
  tokens_out: number | null
  error: string | null
  failure_code?: string | null
  failure_detail?: string | null
  generation_progress?: { done: number; total: number } | null
}

export type ApprovalInfo = {
  approved_by_name: string | null
  approved_at: string
  comment: string | null
  self_approved: boolean
}

export type ProjectStep = {
  key: string
  title: string
  order: number
  implemented: boolean
  status: DerivedStepStatus
  has_failed_attempt: boolean
  can_generate: boolean
  blocked_reason: string | null
  current_version_id: string | null
  can_request_changes: boolean
  can_approve: boolean
  approve_blocked_reason: string | null
  latest_version: StepVersionSummary | null
  layout: StepLayoutSection[]
  reads_description: string
  writes_description: string
  context_steps: StepContextStep[]
  input_fields: StepInputField[]
  export_formats?: string[]
  generation_progress?: { done: number; total: number } | null
  supports_reassemble?: boolean
}

export type ProjectStepsResponse = {
  steps: ProjectStep[]
}

export type StepVersionDetail = {
  id: string
  project_id: string
  step_key: string
  version_no: number
  status: StepVersionStatus
  source: StepVersionSource
  content: Record<string, unknown> | null
  inputs: Record<string, unknown>
  based_on_version_id: string | null
  instructions: string | null
  error: string | null
  model_id: string | null
  prompt_version: string | null
  tokens_in: number | null
  tokens_out: number | null
  created_at: string
  created_by_name: string | null
  generation_started_at: string | null
  generation_finished_at: string | null
  approval: ApprovalInfo | null
  layout?: StepLayoutSection[] | null
}

export type StepVersionPromptResponse = {
  step_version_id: string
  assembled_prompt: string
}

export function getProjectSteps(projectId: string): Promise<ProjectStepsResponse> {
  return apiRequest<ProjectStepsResponse>(`/projects/${projectId}/steps`)
}

export function generateStep(
  projectId: string,
  stepKey: string,
  inputs?: Record<string, unknown>,
): Promise<{ version: StepVersionSummary }> {
  const hasInputs = inputs != null && Object.keys(inputs).length > 0
  return apiRequest<{ version: StepVersionSummary }>(
    `/projects/${projectId}/steps/${stepKey}/generate`,
    hasInputs
      ? {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ inputs }),
        }
      : { method: 'POST' },
  )
}

export function getStepVersions(
  projectId: string,
  stepKey: string,
): Promise<StepVersionSummary[]> {
  return apiRequest<StepVersionSummary[]>(
    `/projects/${projectId}/steps/${stepKey}/versions`,
  )
}

export function getStepVersionDetail(versionId: string): Promise<StepVersionDetail> {
  return apiRequest<StepVersionDetail>(`/step-versions/${versionId}`)
}

export function getStepVersionPrompt(
  versionId: string,
): Promise<StepVersionPromptResponse> {
  return apiRequest<StepVersionPromptResponse>(`/step-versions/${versionId}/prompt`)
}

export function requestStepChanges(
  versionId: string,
  instructions: string | null,
  inputs?: Record<string, unknown>,
  parts?: string[],
): Promise<{ version: StepVersionSummary }> {
  const body: Record<string, unknown> = {}
  if (instructions != null && instructions.trim()) body.instructions = instructions.trim()
  if (inputs != null) body.inputs = inputs
  if (parts != null && parts.length > 0) body.parts = parts
  return apiRequest<{ version: StepVersionSummary }>(
    `/step-versions/${versionId}/request-changes`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

export function approveStepVersion(
  versionId: string,
  comment?: string | null,
): Promise<StepVersionDetail> {
  return apiRequest<StepVersionDetail>(`/step-versions/${versionId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment: comment ?? null }),
  })
}

export function anyStepGenerating(steps: ProjectStep[] | undefined): boolean {
  return steps?.some((s) => s.status === 'generating') ?? false
}

export function downloadStepVersion(
  versionId: string,
  format: string,
  fallbackFilename: string,
): Promise<{ blob: Blob; filename: string }> {
  return apiFetchBlob(
    `/step-versions/${versionId}/download?format=${encodeURIComponent(format)}`,
    fallbackFilename,
  )
}

export function downloadStepVersionDocx(
  versionId: string,
  fallbackFilename: string,
): Promise<{ blob: Blob; filename: string }> {
  return downloadStepVersion(versionId, 'docx', fallbackFilename)
}
