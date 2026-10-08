import {
  groupPermissionsByArea,
  PERMISSION_AREA_LABELS,
  permissionGroupLabel,
  type PermissionArea,
} from '@/lib/permissionLabels'

export const PERMISSION_USER_MANAGE = 'user.manage'
export const PERMISSION_ROLE_MANAGE = 'role.manage'
export const PERMISSION_SETTINGS_MANAGE = 'settings.manage'
export const PERMISSION_PROJECT_VIEW = 'project.view'
export const PERMISSION_PROJECT_CREATE = 'project.create'
export const PERMISSION_PROJECT_ARCHIVE = 'project.archive'
export const PERMISSION_INPUT_ADD = 'input.add'

export const PERMISSION_STEP_GENERATE = 'step.generate'
export const PERMISSION_STEP_REQUEST_CHANGES = 'step.request_changes'
export const PERMISSION_STEP_APPROVE = 'step.approve'
export const PERMISSION_PROMPT_VIEW = 'prompt.view'
export const PERMISSION_DOCUMENT_DOWNLOAD = 'document.download'

export const ADMIN_ROLE_NAME = 'Admin'

export function hasPermission(
  permissions: readonly string[],
  code: string,
): boolean {
  return permissions.includes(code)
}

/** @deprecated Use groupPermissionsByArea for display grouping. */
export function groupPermissionCodes(codes: readonly string[]): Map<string, string[]> {
  const byArea = groupPermissionsByArea(codes)
  const map = new Map<string, string[]>()
  for (const [area, list] of byArea) {
    map.set(area, list)
  }
  return map
}

export function permissionGroupChipLabel(area: PermissionArea, count: number): string {
  return `${PERMISSION_AREA_LABELS[area]} ${count}`
}

export { permissionGroupLabel }
