import { apiRequest } from './client'
import type {
  PermissionOut,
  RoleCreate,
  RoleOut,
  RolePermissionsUpdate,
} from './types'

export function listPermissions(): Promise<PermissionOut[]> {
  return apiRequest<PermissionOut[]>('/permissions')
}

export function listRoles(): Promise<RoleOut[]> {
  return apiRequest<RoleOut[]>('/roles')
}

export function createRole(body: RoleCreate): Promise<RoleOut> {
  return apiRequest<RoleOut>('/roles', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function replaceRolePermissions(
  roleId: string,
  body: RolePermissionsUpdate,
): Promise<RoleOut> {
  return apiRequest<RoleOut>(`/roles/${roleId}/permissions`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}
