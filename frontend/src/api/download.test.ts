import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetchBlob } from './download'
import * as tokenStore from './tokenStore'

describe('apiFetchBlob', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllEnvs()
  })

  beforeEach(() => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000')
  })

  it('uses authorized fetch and never puts token in URL', async () => {
    vi.spyOn(tokenStore, 'getAccessToken').mockReturnValue('secret-token')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['x']), {
        status: 200,
        headers: { 'Content-Disposition': 'attachment; filename="doc.txt"' },
      }),
    )

    const result = await apiFetchBlob('/projects/p1/files/f1/download', 'fallback.txt')
    expect(result.filename).toBe('doc.txt')
    const calledUrl = fetchMock.mock.calls[0]?.[0] as string
    expect(calledUrl).not.toContain('secret-token')
    expect(calledUrl).not.toContain('access_token')
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer secret-token')
  })
})
