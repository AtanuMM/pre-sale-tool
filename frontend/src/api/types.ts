export type UserPublic = {
  id: string
  email: string
  full_name: string
  is_active: boolean
  permissions: string[]
}

export type LoginRequest = {
  email: string
  password: string
}

export type LoginResponse = {
  access_token: string
  token_type: string
  expires_in: number
  user: UserPublic
}

export type RoleBrief = {
  id: string
  name: string
}

export type UserAdmin = {
  id: string
  email: string
  full_name: string
  is_active: boolean
  last_login_at: string | null
  roles: RoleBrief[]
}

export type UserListResponse = {
  items: UserAdmin[]
  total: number
}

export type UserCreate = {
  email: string
  full_name: string
  password: string
  role_ids: string[]
}

export type UserUpdate = {
  full_name?: string
  is_active?: boolean
  role_ids?: string[]
}

export type ResetPasswordRequest = {
  password: string
}

export type PermissionOut = {
  id: string
  code: string
}

export type RoleOut = {
  id: string
  name: string
  description: string | null
  permissions: string[]
}

export type RoleCreate = {
  name: string
  description?: string | null
  permission_codes: string[]
}

export type RolePermissionsUpdate = {
  permission_codes: string[]
}

export type SettingsOut = {
  allow_self_approval: boolean
}

export type SettingsUpdate = {
  allow_self_approval?: boolean
}
