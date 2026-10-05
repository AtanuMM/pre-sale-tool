import { apiRequest, applyLoginResponse } from './client'
import type { LoginRequest, LoginResponse, UserPublic } from './types'

export async function login(body: LoginRequest): Promise<LoginResponse> {
  const data = await apiRequest<LoginResponse>(
    '/auth/login',
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
    { skipAuthRetry: true },
  )
  applyLoginResponse(data)
  return data
}

export async function fetchMe(): Promise<UserPublic> {
  return apiRequest<UserPublic>('/auth/me')
}
