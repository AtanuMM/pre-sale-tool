import type { ProjectStep } from '@/api/steps'
import { WorkflowStepStatusBadge } from '@/components/workflow/WorkflowStepStatusBadge'
import { cn } from '@/lib/utils'

type WorkflowCompactStepperProps = {
  steps: ProjectStep[]
  className?: string
}

export function WorkflowCompactStepper({ steps, className }: WorkflowCompactStepperProps) {
  const sorted = [...steps].sort((a, b) => a.order - b.order)
  return (
    <ol className={cn('flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:gap-2', className)}>
      {sorted.map((step, index) => (
        <li
          key={step.key}
          className="flex min-w-0 flex-1 flex-col gap-1 sm:min-w-[calc(25%-0.5rem)] lg:min-w-0"
        >
          <div className="flex items-start gap-2">
            <span
              className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border bg-muted text-xs font-semibold tabular-nums text-muted-foreground"
              aria-hidden
            >
              {index + 1}
            </span>
            <div className="min-w-0 space-y-1">
              <p className="text-xs font-medium leading-snug">{step.title}</p>
              <WorkflowStepStatusBadge
                status={step.status}
                implemented={step.implemented}
                hasFailedAttempt={step.has_failed_attempt}
              />
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}
