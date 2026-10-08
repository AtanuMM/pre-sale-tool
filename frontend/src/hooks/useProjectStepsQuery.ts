import { useQuery, type QueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { toast } from 'sonner'

import {
  anyStepGenerating,
  getProjectSteps,
  type ProjectStep,
  type ProjectStepsResponse,
} from '@/api/steps'
import { derivedStepStatusLabel } from '@/lib/stepLabels'

export const projectStepsQueryKey = (projectId: string) =>
  ['projects', projectId, 'steps'] as const

const POLL_MS = 3000

export async function refetchProjectStepsImmediately(
  queryClient: QueryClient,
  projectId: string,
): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: projectStepsQueryKey(projectId) })
  await queryClient.refetchQueries({ queryKey: projectStepsQueryKey(projectId) })
}

function settleToastMessage(steps: ProjectStep[]): string {
  const scope = steps.find((s) => s.key === 'scope_analysis')
  if (scope?.status === 'in_review') {
    return 'Analysis ready for review'
  }
  if (scope?.has_failed_attempt || scope?.latest_version?.status === 'failed') {
    return 'Generation failed. Try again when ready.'
  }
  return 'Step generation finished'
}

type UseProjectStepsQueryOptions = {
  enabled?: boolean
  onStatusAnnounce?: (message: string) => void
}

export function useProjectStepsQuery(
  projectId: string | undefined,
  options: UseProjectStepsQueryOptions = {},
) {
  const { enabled = true, onStatusAnnounce } = options
  const prevAnyGeneratingRef = useRef<boolean | null>(null)
  const prevStatusByKeyRef = useRef<Map<string, string>>(new Map())

  const query = useQuery({
    queryKey: projectId ? projectStepsQueryKey(projectId) : ['projects', 'steps', 'none'],
    queryFn: () => getProjectSteps(projectId!),
    enabled: Boolean(projectId) && enabled,
    refetchInterval: (q) => {
      const data = q.state.data as ProjectStepsResponse | undefined
      return anyStepGenerating(data?.steps) ? POLL_MS : false
    },
    refetchIntervalInBackground: false,
  })

  const steps = query.data?.steps

  useEffect(() => {
    if (!steps) return
    const anyGen = anyStepGenerating(steps)
    const prev = prevAnyGeneratingRef.current
    if (prev === null) {
      prevAnyGeneratingRef.current = anyGen
      return
    }
    if (prev === true && !anyGen) {
      toast.message(settleToastMessage(steps))
    }
    prevAnyGeneratingRef.current = anyGen
  }, [steps])

  useEffect(() => {
    if (!steps || !onStatusAnnounce) return
    const nextMap = new Map(steps.map((s) => [s.key, s.status]))
    const prevMap = prevStatusByKeyRef.current
    if (prevMap.size === 0) {
      prevStatusByKeyRef.current = nextMap
      return
    }
    for (const step of steps) {
      const prev = prevMap.get(step.key)
      if (prev !== undefined && prev !== step.status) {
        onStatusAnnounce(
          `${step.title}: ${derivedStepStatusLabel(prev as ProjectStep['status'])} to ${derivedStepStatusLabel(step.status)}`,
        )
      }
    }
    prevStatusByKeyRef.current = nextMap
  }, [steps, onStatusAnnounce])

  return query
}
