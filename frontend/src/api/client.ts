import { ApiError, parseApiError } from './errors'
import type { LoginResponse } from './types'
import { clearAccessToken, getAccessToken, setAccessToken } from './tokenStore'

export function getApiBaseUrl(): string {
  const baseUrl = import.meta.env.VITE_API_BASE_URL
  if (!baseUrl) {
    throw new Error('VITE_API_BASE_URL is not set')
  }
  return baseUrl.replace(/\/$/, '')
}

export function buildUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${getApiBaseUrl()}${normalizedPath}`
}

type SessionClearReason = 'refresh_failed' | 'logout'

type SessionHandlers = {
  onSessionCleared?: (reason: SessionClearReason) => void
}

let sessionHandlers: SessionHandlers = {}
let refreshInFlight: Promise<LoginResponse | null> | null = null

export function setSessionHandlers(handlers: SessionHandlers): void {
  sessionHandlers = handlers
}

/** Test-only reset */
export function resetClientAuthState(): void {
  refreshInFlight = null
  clearAccessToken()
  sessionHandlers = {}
}

function isAuthPath(path: string): boolean {
  return (
    path === '/auth/login' ||
    path === '/auth/refresh' ||
    path === '/auth/logout'
  )
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

async function rawFetch(
  path: string,
  init?: RequestInit,
  accessTokenOverride?: string | null,
): Promise<Response> {
  const token =
    accessTokenOverride !== undefined ? accessTokenOverride : getAccessToken()
  const headers = new Headers(init?.headers)
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  if (
    init?.body !== undefined &&
    init.body !== null &&
    !(init.body instanceof FormData) &&
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json')
  }

  return fetch(buildUrl(path), {
    ...init,
    headers,
    credentials: 'include',
  })
}

export async function refreshSessionSingleFlight(): Promise<LoginResponse | null> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

async function performRefresh(): Promise<LoginResponse | null> {
  const response = await rawFetch('/auth/refresh', { method: 'POST' }, null)
  if (!response.ok) {
    clearAccessToken()
    sessionHandlers.onSessionCleared?.('refresh_failed')
    return null
  }
  const data = await parseJsonResponse<LoginResponse>(response)
  setAccessToken(data.access_token)
  return data
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
  options?: { skipAuthRetry?: boolean },
): Promise<T> {
  let response = await rawFetch(path, init)

  const canRetry =
    response.status === 401 &&
    !options?.skipAuthRetry &&
    !isAuthPath(path)

  if (canRetry) {
    const refreshed = await refreshSessionSingleFlight()
    if (refreshed) {
      response = await rawFetch(path, init)
    } else {
      throw new ApiError(401, 'Not authenticated')
    }
  }

  if (!response.ok) {
    throw await parseApiError(response)
  }

  return parseJsonResponse<T>(response)
}

export async function bootstrapRefresh(): Promise<LoginResponse | null> {
  return refreshSessionSingleFlight()
}

export function applyLoginResponse(data: LoginResponse): void {
  setAccessToken(data.access_token)
}

export function clearSession(): void {
  clearAccessToken()
}

export async function logoutRequest(): Promise<void> {
  try {
    await apiRequest<void>('/auth/logout', { method: 'POST' }, { skipAuthRetry: true })
  } finally {
    clearSession()
  }
}
