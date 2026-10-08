import type { ProjectStatus } from '@/api/projects'
import { Badge } from '@/components/ui/badge'
import { projectStatusLabel } from '@/lib/projectLabels'

const VARIANT: Record<ProjectStatus, 'default' | 'secondary' | 'outline'> = {
  active: 'default',
  completed: 'secondary',
  archived: 'outline',
}

export function ProjectStatusBadge({ status }: { status: ProjectStatus }) {
  return <Badge variant={VARIANT[status]}>{projectStatusLabel(status)}</Badge>
}
