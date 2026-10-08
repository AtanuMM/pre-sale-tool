import type { DerivedStepStatus } from '@/api/steps'
import { Badge } from '@/components/ui/badge'
import { derivedStepStatusLabel } from '@/lib/stepLabels'
import { cn } from '@/lib/utils'
import { Loader2Icon } from 'lucide-react'

type WorkflowStepStatusBadgeProps = {
  status: DerivedStepStatus
  implemented?: boolean
  hasFailedAttempt?: boolean
  className?: string
}

function variantForStatus(
  status: DerivedStepStatus,
): 'secondary' | 'outline' | 'success' | 'inactive' | 'default' {
  switch (status) {
    case 'approved':
      return 'success'
    case 'generating':
      return 'default'
    case 'locked':
      return 'inactive'
    case 'stale':
      return 'outline'
    default:
      return 'secondary'
  }
}

export function WorkflowStepStatusBadge({
  status,
  implemented = true,
  hasFailedAttempt = false,
  className,
}: WorkflowStepStatusBadgeProps) {
  const label = implemented ? derivedStepStatusLabel(status) : 'Coming soon'
  const badgeVariant = implemented ? variantForStatus(status) : 'inactive'
  return (
    <span className={cn('inline-flex flex-wrap items-center gap-1.5', className)}>
      <Badge variant={badgeVariant} className="gap-1">
        {implemented && status === 'generating' ? (
          <Loader2Icon className="size-3 animate-spin" aria-hidden />
        ) : null}
        <span>{label}</span>
      </Badge>
      {hasFailedAttempt ? (
        <Badge variant="outline" className="border-destructive/40 text-destructive">
          Failed attempt
        </Badge>
      ) : null}
    </span>
  )
}
