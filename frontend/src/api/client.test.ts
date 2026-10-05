import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  apiRequest,
  resetClientAuthState,
  setSessionHandlers,
} from './client'
import { setAccessToken } from './tokenStore'
import type { LoginResponse } from './types'

const refreshPayload: LoginResponse = {
  access_token: 'new-access-token',
  token_type: 'bearer',
  expires_in: 900,
  user: {
    id: 'u1',
    email: 'a@example.com',
    full_name: 'Admin',
    is_active: true,
    permissions: ['user.manage'],
  },
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('apiRequest auth retry', () => {
  beforeEach(() => {
    resetClientAuthState()
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses single-flight refresh and retries the original request once', async () => {
    setAccessToken('stale-token')
    const fetchMock = vi.mocked(fetch)
    let usersCalls = 0
    let refreshCalls = 0

    fetchMock.mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/auth/refresh')) {
        refreshCalls += 1
        return Promise.resolve(jsonResponse(refreshPayload))
      }
      if (url.endsWith('/users')) {
        usersCalls += 1
        if (usersCalls === 1) {
          return Promise.resolve(jsonResponse({ detail: 'Not authenticated' }, 401))
        }
        return Promise.resolve(jsonResponse({ items: [], total: 0 }))
      }
      return Promise.resolve(jsonResponse({}, 404))
    })

    const [a, b] = await Promise.all([
      apiRequest<{ items: unknown[]; total: number }>('/users'),
      apiRequest<{ items: unknown[]; total: number }>('/users'),
    ])

    expect(refreshCalls).toBe(1)
    expect(usersCalls).toBeGreaterThanOrEqual(2)
    expect(a.total).toBe(0)
    expect(b.total).toBe(0)
  })

  it('clears session and invokes handler when refresh fails', async () => {
    setAccessToken('stale-token')
    const onSessionCleared = vi.fn()
    setSessionHandlers({ onSessionCleared })

    const fetchMock = vi.mocked(fetch)
    fetchMock.mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/auth/refresh')) {
        return Promise.resolve(jsonResponse({ detail: 'Not authenticated' }, 401))
      }
      if (url.endsWith('/protected')) {
        return Promise.resolve(jsonResponse({ detail: 'Not authenticated' }, 401))
      }
      return Promise.resolve(jsonResponse({}, 404))
    })

    await expect(apiRequest('/protected')).rejects.toMatchObject({ status: 401 })
    expect(onSessionCleared).toHaveBeenCalledTimes(1)
  })

  it('does not refresh in a loop when retry still returns 401', async () => {
    setAccessToken('stale-token')
    const fetchMock = vi.mocked(fetch)
    let refreshCalls = 0

    fetchMock.mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/auth/refresh')) {
        refreshCalls += 1
        return Promise.resolve(jsonResponse(refreshPayload))
      }
      if (url.endsWith('/protected')) {
        return Promise.resolve(jsonResponse({ detail: 'Not authenticated' }, 401))
      }
      return Promise.resolve(jsonResponse({}, 404))
    })

    await expect(apiRequest('/protected')).rejects.toMatchObject({ status: 401 })
    expect(refreshCalls).toBe(1)
  })
})
