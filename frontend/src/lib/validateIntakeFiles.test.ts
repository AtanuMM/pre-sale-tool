import { describe, expect, it } from 'vitest'

import type { ProjectIntakeLimits } from '@/api/projects'
import {
  isReceivedAtInFuture,
  localDateTimeInputToIso,
  validateSelectedFiles,
} from '@/lib/validateIntakeFiles'

const LIMITS: ProjectIntakeLimits = {
  max_file_bytes: 1000,
  max_files_per_input: 10,
  allowed_extensions: ['txt', 'pdf'],
  max_extracted_chars: 500_000,
}

function file(name: string, size: number, type = 'text/plain'): File {
  return new File([new Uint8Array(size)], name, { type })
}

describe('validateSelectedFiles', () => {
  it('rejects disallowed type', () => {
    const { valid, issues } = validateSelectedFiles([file('x.exe', 10)], LIMITS)
    expect(valid).toHaveLength(0)
    expect(issues[0]?.message).toMatch(/not allowed/)
  })

  it('rejects oversize file', () => {
    const { valid, issues } = validateSelectedFiles([file('a.txt', 1001)], LIMITS)
    expect(valid).toHaveLength(0)
    expect(issues[0]?.message).toMatch(/maximum size/)
  })

  it('rejects 11th file', () => {
    const files = Array.from({ length: 11 }, (_, i) => file(`f${i}.txt`, 10))
    const { valid, issues } = validateSelectedFiles(files, LIMITS)
    expect(valid).toHaveLength(10)
    expect(issues.length).toBeGreaterThan(0)
  })
})

describe('intake datetime', () => {
  it('rejects future received-at', () => {
    const future = new Date(Date.now() + 3600_000)
    const pad = (n: number) => String(n).padStart(2, '0')
    const local = `${future.getFullYear()}-${pad(future.getMonth() + 1)}-${pad(future.getDate())}T${pad(future.getHours())}:${pad(future.getMinutes())}`
    expect(isReceivedAtInFuture(local)).toBe(true)
  })

  it('builds ISO for multipart', () => {
    const iso = localDateTimeInputToIso('2026-01-15T10:30')
    expect(iso).toContain('2026')
  })
})
