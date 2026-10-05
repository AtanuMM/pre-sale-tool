export type PermissionArea =
  | 'project'
  | 'input'
  | 'step'
  | 'document'
  | 'reference'
  | 'template'
  | 'prompt'
  | 'audit'
  | 'admin'

export const PERMISSION_AREA_LABELS: Record<PermissionArea, string> = {
  project: 'Projects',
  input: 'Intake',
  step: 'Workflow steps',
  document: 'Documents',
  reference: 'References',
  template: 'Templates',
  prompt: 'Prompts',
  audit: 'Audit',
  admin: 'Administration',
}

export const PERMISSION_CODE_LABELS: Record<string, string> = {
  'project.create': 'Create projects',
  'project.view': 'View projects',
  'project.archive': 'Archive projects',
  'input.add': 'Add intake inputs',
  'step.generate': 'Generate steps',
  'step.request_changes': 'Request changes',
  'step.edit': 'Edit step output',
  'step.approve': 'Approve steps',
  'step.reopen': 'Reopen approved steps',
  'document.download': 'Download documents',
  'reference.view': 'View references',
  'reference.manage': 'Manage references',
  'template.view': 'View templates',
  'template.manage': 'Manage templates',
  'prompt.view': 'View assembled prompts',
  'audit.view': 'View audit log',
  'audit.export': 'Export audit log',
  'user.manage': 'Manage users',
  'role.manage': 'Manage roles',
  'settings.manage': 'Manage settings',
}

const ADMIN_PREFIXES = new Set(['user', 'role', 'settings'])

export function permissionArea(code: string): PermissionArea {
  const dot = code.indexOf('.')
  const prefix = dot === -1 ? '' : code.slice(0, dot)
  if (ADMIN_PREFIXES.has(prefix)) return 'admin'
  if (prefix === 'input') return 'input'
  if (prefix in PERMISSION_AREA_LABELS) {
    return prefix as PermissionArea
  }
  return 'audit'
}

export function groupPermissionsByArea(codes: readonly string[]): Map<PermissionArea, string[]> {
  const map = new Map<PermissionArea, string[]>()
  for (const code of codes) {
    const area = permissionArea(code)
    const list = map.get(area)
    if (list) list.push(code)
    else map.set(area, [code])
  }
  for (const list of map.values()) {
    list.sort()
  }
  return new Map(
    [...map.entries()].sort(([a], [b]) =>
      PERMISSION_AREA_LABELS[a].localeCompare(PERMISSION_AREA_LABELS[b]),
    ),
  )
}

export function permissionLabel(code: string): string {
  return PERMISSION_CODE_LABELS[code] ?? code
}

/** Readable group label for permission prefix keys (roles UI). */
export function permissionGroupLabel(groupKey: string): string {
  if (ADMIN_PREFIXES.has(groupKey)) return PERMISSION_AREA_LABELS.admin
  if (groupKey === 'input') return PERMISSION_AREA_LABELS.input
  if (groupKey in PERMISSION_AREA_LABELS) {
    return PERMISSION_AREA_LABELS[groupKey as PermissionArea]
  }
  return groupKey
}

export function groupPermissionCodesByDisplay(
  codes: readonly string[],
): Map<PermissionArea, string[]> {
  return groupPermissionsByArea(codes)
}
