import type { ExtractionStatus, InputKind, ProjectStatus } from '@/api/projects'

export const INPUT_KIND_OPTIONS: { value: InputKind; label: string }[] = [
  { value: 'email', label: 'Email' },
  { value: 'document', label: 'Document' },
  { value: 'meeting_notes', label: 'Meeting notes' },
  { value: 'other', label: 'Other' },
]

export function projectStatusLabel(status: ProjectStatus): string {
  switch (status) {
    case 'active':
      return 'Active'
    case 'completed':
      return 'Completed'
    case 'archived':
      return 'Archived'
    default:
      return status
  }
}

export function extractionStatusLabel(status: ExtractionStatus): string {
  switch (status) {
    case 'ok':
      return 'OK'
    case 'empty':
      return 'No text found'
    case 'truncated':
      return 'Truncated'
    default:
      return status
  }
}

export function shortSha256(sha: string): string {
  if (sha.length <= 12) return sha
  return `${sha.slice(0, 8)}…${sha.slice(-4)}`
}
