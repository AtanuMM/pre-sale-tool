/** Display-only role inference from permission sets (matches backend seed bundles). */

const ALL_PERMISSIONS = [
  'project.create',
  'project.view',
  'project.archive',
  'input.add',
  'step.generate',
  'step.request_changes',
  'step.edit',
  'step.approve',
  'step.reopen',
  'document.download',
  'reference.view',
  'reference.manage',
  'template.view',
  'template.manage',
  'prompt.view',
  'audit.view',
  'audit.export',
  'user.manage',
  'role.manage',
  'settings.manage',
] as const

const ROLE_BUNDLES: Record<string, readonly string[]> = {
  Admin: ALL_PERMISSIONS,
  Lead: [
    'project.create',
    'project.view',
    'input.add',
    'step.generate',
    'step.request_changes',
    'step.edit',
    'step.approve',
    'step.reopen',
    'document.download',
    'reference.view',
    'template.view',
    'prompt.view',
    'audit.view',
  ],
  Analyst: [
    'project.create',
    'project.view',
    'input.add',
    'step.generate',
    'step.request_changes',
    'step.edit',
    'step.approve',
    'document.download',
    'reference.view',
    'template.view',
  ],
  Viewer: ['project.view', 'document.download', 'reference.view', 'template.view'],
}

function setsEqual(a: Set<string>, b: readonly string[]): boolean {
  if (a.size !== b.length) return false
  return b.every((code) => a.has(code))
}

export function inferRoleLabels(permissions: readonly string[]): string[] {
  const set = new Set(permissions)
  const matched: string[] = []
  for (const [role, codes] of Object.entries(ROLE_BUNDLES)) {
    if (setsEqual(set, codes)) {
      matched.push(role)
    }
  }
  if (matched.length > 0) {
    return matched
  }
  return permissions.length > 0 ? ['Custom access'] : []
}
