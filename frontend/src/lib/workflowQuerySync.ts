import type { QueryClient } from '@tanstack/react-query'

import { projectStepsQueryKey } from '@/hooks/useProjectStepsQuery'

export async function syncWorkflowAfterMutation(
  queryClient: QueryClient,
  projectId: string,
  stepKey: string,
  versionId?: string,
): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: projectStepsQueryKey(projectId) })
  await queryClient.refetchQueries({ queryKey: projectStepsQueryKey(projectId) })
  await queryClient.invalidateQueries({
    queryKey: ['projects', projectId, 'steps', stepKey, 'versions'],
  })
  if (versionId) {
    await queryClient.invalidateQueries({ queryKey: ['step-versions', versionId] })
  }
  await queryClient.invalidateQueries({ queryKey: ['projects', projectId] })
}

export async function syncWorkflowAfter409(
  queryClient: QueryClient,
  projectId: string,
  stepKey: string,
  versionId?: string,
): Promise<void> {
  await syncWorkflowAfterMutation(queryClient, projectId, stepKey, versionId)
}
