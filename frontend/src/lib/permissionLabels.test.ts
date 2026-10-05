import { describe, expect, it } from 'vitest'

import {
  groupPermissionsByArea,
  PERMISSION_AREA_LABELS,
  permissionArea,
} from '@/lib/permissionLabels'

describe('permissionLabels', () => {
  it('maps intake and administration prefixes without an Other group', () => {
    expect(permissionArea('input.add')).toBe('input')
    expect(permissionArea('user.manage')).toBe('admin')
    expect(permissionArea('role.manage')).toBe('admin')
    expect(permissionArea('settings.manage')).toBe('admin')

    const codes = [
      'project.view',
      'input.add',
      'step.approve',
      'user.manage',
      'audit.view',
    ]
    const grouped = groupPermissionsByArea(codes)
    expect(grouped.has('other' as keyof typeof PERMISSION_AREA_LABELS)).toBe(false)
    expect([...grouped.keys()]).not.toContain('other')
    expect(grouped.get('input')).toEqual(['input.add'])
    expect(grouped.get('admin')).toEqual(['user.manage'])
  })
})
