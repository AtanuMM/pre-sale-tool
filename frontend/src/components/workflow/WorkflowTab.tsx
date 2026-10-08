import { useEffect, useState } from 'react'

import type { InputRecord } from '@/api/projects'
import type { ProjectStep } from '@/api/steps'
import { StepPanel } from '@/components/workflow/StepPanel'
import { WorkflowStepList } from '@/components/workflow/WorkflowStepList'
import { pickDefaultStepKey } from '@/components/workflow/workflowSelection'
import { Skeleton } from '@/components/ui/skeleton'

type WorkflowTabProps = {
  projectId: string
  steps: ProjectStep[] | undefined
  stepsLoading: boolean
  initialInput: InputRecord | undefined
  hasPermission: (code: string) => boolean
  initialStepKey?: string | null
  liveMessage: string
}

export function WorkflowTab({
  projectId,
  steps,
  stepsLoading,
  initialInput,
  hasPermission,
  initialStepKey,
  liveMessage,
}: WorkflowTabProps) {
  const [selectedKey, setSelectedKey] = useState<string>('scope_analysis')

  useEffect(() => {
    if (initialStepKey && steps?.some((s) => s.key === initialStepKey)) {
      setSelectedKey(initialStepKey)
    }
  }, [initialStepKey, steps])

  useEffect(() => {
    if (!steps?.length) return
    setSelectedKey((cur) =>
      steps.some((s) => s.key === cur) ? cur : pickDefaultStepKey(steps),
    )
  }, [steps])

  const selected = steps?.find((s) => s.key === selectedKey)

  return (
    <div className="space-y-4">
      <div
        className="sr-only"
        aria-live="polite"
        aria-atomic="true"
        role="status"
      >
        {liveMessage}
      </div>
      {stepsLoading || !steps ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
          <WorkflowStepList
            steps={steps}
            selectedKey={selectedKey}
            onSelect={setSelectedKey}
          />
          <div className="min-w-0 flex-1">
            {selected ? (
              <StepPanel
                projectId={projectId}
                step={selected}
                initialInput={initialInput}
                hasPermission={hasPermission}
              />
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}
