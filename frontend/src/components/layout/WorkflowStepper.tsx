import { cn } from '@/lib/utils'

const WORKFLOW_STEPS = [
  'Scope analysis',
  'Gap analysis',
  'Feature list',
  'Estimate',
  'SOW',
  'SRS',
  'Sprint plan',
  'FRS',
] as const

type WorkflowStepperProps = {
  footnote?: string
}

export function WorkflowStepper({
  footnote = 'Project workflow steps will appear here once project workspaces are available.',
}: WorkflowStepperProps) {
  return (
    <div className="w-full">
      <ol className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:gap-2">
        {WORKFLOW_STEPS.map((step, index) => (
          <li
            key={step}
            className={cn(
              'flex min-w-0 flex-1 items-center gap-2 sm:min-w-[calc(25%-0.5rem)] sm:flex-col sm:items-start lg:min-w-0 lg:flex-1',
            )}
          >
            <div className="flex w-full items-center gap-2 sm:flex-col sm:items-start">
              <span
                className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border bg-muted text-xs font-semibold tabular-nums text-muted-foreground"
                aria-hidden
              >
                {index + 1}
              </span>
              <span className="text-xs font-medium leading-snug text-muted-foreground">{step}</span>
            </div>
            {index < WORKFLOW_STEPS.length - 1 && (
              <span
                className="hidden h-px flex-1 bg-border sm:mx-1 sm:mt-4 sm:block lg:hidden"
                aria-hidden
              />
            )}
          </li>
        ))}
      </ol>
      <p className="mt-4 text-xs text-muted-foreground">{footnote}</p>
    </div>
  )
}
