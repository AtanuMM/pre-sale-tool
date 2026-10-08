import { apiRequest } from './client'
import { apiFetchBlob } from './download'

export type InputKind = 'email' | 'document' | 'meeting_notes' | 'other'
export type ProjectStatus = 'active' | 'completed' | 'archived'
export type ExtractionStatus = 'ok' | 'empty' | 'truncated'

export type ProjectListItem = {
  id: string
  name: string
  client_name: string
  status: ProjectStatus
  created_by_name: string | null
  created_at: string
}

export type ProjectListResponse = {
  items: ProjectListItem[]
  total: number
}

export type FileSummary = {
  id: string
  original_name: string
  mime_type: string
  size_bytes: number
  sha256: string
  extraction_status: ExtractionStatus
  extracted_char_count: number
}

export type InputRecord = {
  id: string
  kind: InputKind
  received_at: string
  received_from: string | null
  subject: string | null
  body: string
  is_followup: boolean
  created_by_name: string | null
  created_at: string
  files: FileSummary[]
}

export type TimelineEntry = {
  action: string
  actor_name: string
  occurred_at: string
}

export type ProjectSummary = {
  id: string
  name: string
  client_name: string
  status: ProjectStatus
  allow_self_approval: boolean | null
  created_by_name: string | null
  created_at: string
  completed_at: string | null
}

export type ProjectOverview = {
  project: ProjectSummary
  effective_allow_self_approval: boolean
  inputs: InputRecord[]
  timeline: TimelineEntry[]
}

export type ProjectCreateResponse = {
  project: ProjectSummary
  input: InputRecord
  files: FileSummary[]
}

export type FileTextResponse = {
  extraction_status: ExtractionStatus
  extracted_char_count: number
  text: string
}

export type ProjectSettingsResponse = {
  allow_self_approval: boolean | null
  effective_allow_self_approval: boolean
}

export type ProjectIntakeLimits = {
  max_file_bytes: number
  max_files_per_input: number
  allowed_extensions: string[]
  max_extracted_chars: number
}

export type ListProjectsParams = {
  limit?: number
  offset?: number
  search?: string
  status?: ProjectStatus
}

export type CreateProjectIntakeFields = {
  name: string
  client_name: string
  kind: InputKind
  received_at: string
  received_from?: string
  subject?: string
  body: string
  files?: File[]
}

/** Follow-up POST accepts the same multipart fields as create (including name/client_name). */
export type FollowUpIntakeFields = Omit<CreateProjectIntakeFields, 'name' | 'client_name'> & {
  name: string
  client_name: string
}

function appendIntakeFormData(form: FormData, fields: CreateProjectIntakeFields): void {
  form.append('name', fields.name)
  form.append('client_name', fields.client_name)
  form.append('kind', fields.kind)
  form.append('received_at', fields.received_at)
  if (fields.received_from?.trim()) {
    form.append('received_from', fields.received_from.trim())
  }
  if (fields.subject?.trim()) {
    form.append('subject', fields.subject.trim())
  }
  form.append('body', fields.body)
  for (const file of fields.files ?? []) {
    form.append('files', file, file.name)
  }
}

export function buildCreateProjectFormData(fields: CreateProjectIntakeFields): FormData {
  const form = new FormData()
  appendIntakeFormData(form, fields)
  return form
}

export function buildFollowUpFormData(fields: FollowUpIntakeFields): FormData {
  const form = new FormData()
  appendIntakeFormData(form, fields)
  return form
}

export function getProjectIntakeLimits(): Promise<ProjectIntakeLimits> {
  return apiRequest<ProjectIntakeLimits>('/projects/limits')
}

export function listProjects(params: ListProjectsParams = {}): Promise<ProjectListResponse> {
  const search = new URLSearchParams()
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  if (params.offset !== undefined) search.set('offset', String(params.offset))
  if (params.search?.trim()) search.set('search', params.search.trim())
  if (params.status) search.set('status', params.status)
  const qs = search.toString()
  return apiRequest<ProjectListResponse>(`/projects${qs ? `?${qs}` : ''}`)
}

export function getProjectOverview(projectId: string): Promise<ProjectOverview> {
  return apiRequest<ProjectOverview>(`/projects/${projectId}/overview`)
}

export function createProject(form: FormData): Promise<ProjectCreateResponse> {
  return apiRequest<ProjectCreateResponse>('/projects', {
    method: 'POST',
    body: form,
  })
}

export function createFollowUpInput(
  projectId: string,
  form: FormData,
): Promise<ProjectCreateResponse> {
  return apiRequest<ProjectCreateResponse>(`/projects/${projectId}/inputs`, {
    method: 'POST',
    body: form,
  })
}

export function archiveProject(projectId: string): Promise<ProjectSummary> {
  return apiRequest<ProjectSummary>(`/projects/${projectId}/archive`, { method: 'POST' })
}

export function restoreProject(projectId: string): Promise<ProjectSummary> {
  return apiRequest<ProjectSummary>(`/projects/${projectId}/restore`, { method: 'POST' })
}

export function patchProjectSettings(
  projectId: string,
  allow_self_approval: boolean | null,
): Promise<ProjectSettingsResponse> {
  return apiRequest<ProjectSettingsResponse>(`/projects/${projectId}/settings`, {
    method: 'PATCH',
    body: JSON.stringify({ allow_self_approval }),
  })
}

export function getProjectFileText(
  projectId: string,
  fileId: string,
): Promise<FileTextResponse> {
  return apiRequest<FileTextResponse>(`/projects/${projectId}/files/${fileId}/text`)
}

export function downloadProjectFile(
  projectId: string,
  fileId: string,
  fallbackName: string,
): Promise<{ blob: Blob; filename: string }> {
  return apiFetchBlob(`/projects/${projectId}/files/${fileId}/download`, fallbackName)
}
