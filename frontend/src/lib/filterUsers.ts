import type { UserAdmin } from '@/api/types'

export type UserStatusFilter = 'all' | 'active' | 'inactive'

export function filterUsers(
  users: UserAdmin[],
  search: string,
  status: UserStatusFilter,
): UserAdmin[] {
  const q = search.trim().toLowerCase()
  return users.filter((u) => {
    if (status === 'active' && !u.is_active) return false
    if (status === 'inactive' && u.is_active) return false
    if (!q) return true
    return (
      u.email.toLowerCase().includes(q) ||
      u.full_name.toLowerCase().includes(q) ||
      u.roles.some((r) => r.name.toLowerCase().includes(q))
    )
  })
}
