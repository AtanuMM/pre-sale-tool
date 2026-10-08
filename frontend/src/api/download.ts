import { buildUrl, refreshSessionSingleFlight } from './client'
import { parseApiError } from './errors'
import { getAccessToken } from './tokenStore'

function parseContentDispositionFilename(header: string | null): string | null {
  if (!header) return null
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1].trim())
    } catch {
      return utf8[1].trim()
    }
  }
  const plain = /filename="([^"]+)"/i.exec(header) ?? /filename=([^;]+)/i.exec(header)
  return plain?.[1]?.trim().replace(/^"|"$/g, '') ?? null
}

async function authorizedFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = getAccessToken()
  const headers = new Headers(init?.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  let response = await fetch(buildUrl(path), {
    ...init,
    headers,
    credentials: 'include',
  })
  if (response.status === 401 && path !== '/auth/login') {
    const refreshed = await refreshSessionSingleFlight()
    if (refreshed) {
      headers.set('Authorization', `Bearer ${refreshed.access_token}`)
      response = await fetch(buildUrl(path), {
        ...init,
        headers,
        credentials: 'include',
      })
    }
  }
  return response
}

/** Fetch binary response with in-memory token (never put token in URL). */
export async function apiFetchBlob(
  path: string,
  fallbackFilename: string,
): Promise<{ blob: Blob; filename: string }> {
  if (path.includes('access_token=') || path.includes('token=')) {
    throw new Error('Refusing download URL that embeds credentials')
  }
  const response = await authorizedFetch(path)
  if (!response.ok) {
    throw await parseApiError(response)
  }
  const blob = await response.blob()
  const fromHeader = parseContentDispositionFilename(response.headers.get('Content-Disposition'))
  return { blob, filename: fromHeader ?? fallbackFilename }
}

export function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.rel = 'noopener'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
