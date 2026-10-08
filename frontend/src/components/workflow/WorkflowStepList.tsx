import type { ProjectStep } from '@/api/steps'
import { WorkflowStepStatusBadge } from '@/components/workflow/WorkflowStepStatusBadge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type WorkflowStepListProps = {
  steps: ProjectStep[]
  selectedKey: string
  onSelect: (key: string) => void
}

export function WorkflowStepList({ steps, selectedKey, onSelect }: WorkflowStepListProps) {
  const sorted = [...steps].sort((a, b) => a.order - b.order)
  return (
    <nav aria-label="Workflow steps" className="min-w-0">
      <ol
        className={cn(
          'flex gap-2 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible lg:pb-0',
        )}
      >
        {sorted.map((step, index) => {
          const selected = step.key === selectedKey
          return (
            <li key={step.key} className="shrink-0 lg:shrink">
              <Button
                type="button"
                variant={selected ? 'secondary' : 'ghost'}
                className={cn(
                  'h-auto w-[11rem] flex-col items-start gap-2 px-3 py-3 text-left lg:w-full',
                  selected && 'ring-1 ring-ring',
                )}
                onClick={() => onSelect(step.key)}
                aria-current={selected ? 'step' : undefined}
              >
                <span className="flex w-full items-center gap-2 text-xs text-muted-foreground">
                  <span
                    className="flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-muted font-semibold tabular-nums"
                    aria-hidden
                  >
                    {index + 1}
                  </span>
                  <span className="font-medium text-foreground">{step.title}</span>
                </span>
                <WorkflowStepStatusBadge
                  status={step.status}
                  implemented={step.implemented}
                  hasFailedAttempt={step.has_failed_attempt}
                />
              </Button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
