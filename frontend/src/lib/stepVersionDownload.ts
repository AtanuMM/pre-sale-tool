import type { StepVersionStatus } from '@/api/steps'

const NO_CONTENT_STATUSES: readonly StepVersionStatus[] = [
  'queued',
  'generating',
  'failed',
]

export function stepVersionCanDownload(status: StepVersionStatus): boolean {
  return !NO_CONTENT_STATUSES.includes(status)
}

export function stepVersionDownloadLabel(status: StepVersionStatus): string {
  return status === 'approved' ? 'Download .docx' : 'Download draft .docx'
}

export function stepVersionDownloadToastError(status: number, message: string): string {
  if (status === 404) return 'Version not found.'
  if (status === 409) return 'No content to download for this version.'
  if (status === 413) return message || 'This version is too large to export.'
  return message || 'Download failed.'
}
