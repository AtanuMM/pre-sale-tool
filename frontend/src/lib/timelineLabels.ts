const ACTION_LABELS: Record<string, string> = {
  'project.created': 'Project created',
  'input.added': 'Client message added',
  'document.downloaded': 'Document downloaded',
  'project.archived': 'Project archived',
  'project.restored': 'Project restored',
  'project.settings_changed': 'Project settings changed',
  'step.generate_requested': 'Step generation requested',
  'step.generated': 'Step output generated',
  'step.generation_failed': 'Step generation failed',
  'step.changes_requested': 'Changes requested on a step',
  'step.approved': 'Step approved',
  'prompt.viewed': 'Prompt viewed (logged)',
}

export function timelineActionLabel(action: string): string {
  const label = ACTION_LABELS[action]
  if (label) return label
  const humanized = action
    .replace(/\./g, ' ')
    .replace(/_/g, ' ')
    .trim()
  if (!humanized) return 'Activity recorded'
  return humanized.charAt(0).toUpperCase() + humanized.slice(1)
}
