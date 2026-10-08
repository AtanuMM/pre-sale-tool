import type { ProjectIntakeLimits } from '@/api/projects'

export type SelectedFileIssue = {
  file: File
  message: string
}

export type ValidateFilesResult = {
  valid: File[]
  issues: SelectedFileIssue[]
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  if (dot <= 0) return ''
  return name.slice(dot + 1).toLowerCase()
}

export function validateSelectedFiles(
  files: File[],
  limits: ProjectIntakeLimits,
): ValidateFilesResult {
  const allowed = new Set(limits.allowed_extensions.map((e) => e.toLowerCase()))
  const issues: SelectedFileIssue[] = []
  const valid: File[] = []

  if (files.length > limits.max_files_per_input) {
    for (const file of files.slice(limits.max_files_per_input)) {
      issues.push({
        file,
        message: `At most ${limits.max_files_per_input} files allowed per input`,
      })
    }
    files = files.slice(0, limits.max_files_per_input)
  }

  for (const file of files) {
    const ext = extensionOf(file.name)
    if (!ext || !allowed.has(ext)) {
      issues.push({
        file,
        message: `File type not allowed. Use: ${limits.allowed_extensions.join(', ')}`,
      })
      continue
    }
    if (file.size > limits.max_file_bytes) {
      issues.push({
        file,
        message: `File exceeds maximum size of ${formatBytes(limits.max_file_bytes)}`,
      })
      continue
    }
    valid.push(file)
  }

  return { valid, issues }
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function localDateTimeInputValue(date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function localDateTimeInputToIso(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    throw new Error('Invalid date')
  }
  return parsed.toISOString()
}

export function isReceivedAtInFuture(localDateTimeValue: string, now = new Date()): boolean {
  const parsed = new Date(localDateTimeValue)
  if (Number.isNaN(parsed.getTime())) return true
  return parsed.getTime() > now.getTime()
}
