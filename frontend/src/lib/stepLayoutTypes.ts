export type StepLayoutColumn = {
  key: string
  header: string
}

export type StepLayoutSection = {
  key: string
  title: string
  kind: 'text' | 'list' | 'table' | 'records' | 'numbered_list'
  copyable?: boolean
  columns?: StepLayoutColumn[]
  record_fields?: StepLayoutColumn[]
  badge_fields?: string[]
}

export type StepContextStep = {
  key: string
  title: string
}

export function sectionDomId(key: string): string {
  return key.replace(/_/g, '-')
}

export function humanizeBadgeField(field: string, value: string): string {
  const label = field.replace(/_/g, ' ')
  const pretty = value.replace(/_/g, ' ')
  const titled =
    pretty.length > 0 ? pretty.charAt(0).toUpperCase() + pretty.slice(1) : pretty
  return `${label.charAt(0).toUpperCase() + label.slice(1)}: ${titled}`
}
