import { apiRequest } from './client'
import type { SettingsOut, SettingsUpdate } from './types'

export function getSettings(): Promise<SettingsOut> {
  return apiRequest<SettingsOut>('/settings')
}

export function updateSettings(body: SettingsUpdate): Promise<SettingsOut> {
  return apiRequest<SettingsOut>('/settings', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}
