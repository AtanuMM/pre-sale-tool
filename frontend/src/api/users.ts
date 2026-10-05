import { apiRequest } from './client'
import type {
  ResetPasswordRequest,
  UserAdmin,
  UserCreate,
  UserListResponse,
  UserUpdate,
} from './types'

export type ListUsersParams = {
  limit?: number
  offset?: number
}

export function listUsers(params: ListUsersParams = {}): Promise<UserListResponse> {
  const search = new URLSearchParams()
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  if (params.offset !== undefined) search.set('offset', String(params.offset))
  const qs = search.toString()
  return apiRequest<UserListResponse>(`/users${qs ? `?${qs}` : ''}`)
}

export function createUser(body: UserCreate): Promise<UserAdmin> {
  return apiRequest<UserAdmin>('/users', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateUser(userId: string, body: UserUpdate): Promise<UserAdmin> {
  return apiRequest<UserAdmin>(`/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function resetUserPassword(
  userId: string,
  body: ResetPasswordRequest,
): Promise<void> {
  return apiRequest<void>(`/users/${userId}/reset-password`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
