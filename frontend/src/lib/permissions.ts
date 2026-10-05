import {
  groupPermissionsByArea,
  PERMISSION_AREA_LABELS,
  permissionGroupLabel,
  type PermissionArea,
} from '@/lib/permissionLabels'

export const PERMISSION_USER_MANAGE = 'user.manage'
export const PERMISSION_ROLE_MANAGE = 'role.manage'
export const PERMISSION_SETTINGS_MANAGE = 'settings.manage'

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
