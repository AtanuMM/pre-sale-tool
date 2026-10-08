import { describe, expect, it } from 'vitest'

import { buildCreateProjectFormData } from '@/api/projects'

describe('buildCreateProjectFormData', () => {
  it('includes expected multipart fields', () => {
    const form = buildCreateProjectFormData({
      name: 'Proj',
      client_name: 'Client',
      kind: 'email',
      received_at: '2026-01-01T12:00:00.000Z',
      body: 'Hello',
      files: [new File(['hi'], 'a.txt', { type: 'text/plain' })],
    })
    expect(form.get('name')).toBe('Proj')
    expect(form.get('client_name')).toBe('Client')
    expect(form.get('kind')).toBe('email')
    expect(form.get('received_at')).toBe('2026-01-01T12:00:00.000Z')
    expect(form.get('body')).toBe('Hello')
    expect(form.getAll('files')).toHaveLength(1)
  })
})
