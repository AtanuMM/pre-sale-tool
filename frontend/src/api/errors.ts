export type ValidationErrorItem = {
  loc: (string | number)[]
  msg: string
  type?: string
}

export type ApiErrorDetail = string | ValidationErrorItem[]

export class ApiError extends Error {
  readonly status: number
  readonly detail: ApiErrorDetail

  constructor(status: number, detail: ApiErrorDetail, message?: string) {
    super(message ?? ApiError.formatDetail(detail))
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }

  static formatDetail(detail: ApiErrorDetail): string {
    if (typeof detail === 'string') {
      return detail
    }
    return detail
      .map((item) => {
        const path = item.loc.filter((part) => part !== 'body').join('.')
        return path ? `${path}: ${item.msg}` : item.msg
      })
      .join('; ')
  }

  displayMessage(): string {
    return ApiError.formatDetail(this.detail)
  }
}

export async function parseApiError(response: Response): Promise<ApiError> {
  let detail: ApiErrorDetail = response.statusText
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body) {
      const raw = (body as { detail: unknown }).detail
      if (typeof raw === 'string' || Array.isArray(raw)) {
        detail = raw as ApiErrorDetail
      }
    }
  } catch {
    /* use statusText */
  }
  return new ApiError(response.status, detail)
}
