export type StepLayoutColumn = {
  key: string
  header: string
}

export type StepLayoutGroupSource = {
  section: string
  key_field: string
  intro_field: string
}

export type StepLayoutSection = {
  key: string
  title: string
  kind:
    | 'text'
    | 'list'
    | 'table'
    | 'records'
    | 'numbered_list'
    | 'stats'
    | 'computed_cards'
    | 'computed_table'
    | 'warning_strip'
    | 'method_note'
    | 'open_items'
    | 'standard_terms'
    | 'rich_text'
    | 'health_panel'
    | 'diagram'
    | 'requirement_table'
  copyable?: boolean
  diagramKey?: string
  columns?: StepLayoutColumn[]
  record_fields?: StepLayoutColumn[]
  badge_fields?: string[]
  ref_prefix?: string
  id_field?: string
  chip_fields?: string[]
  group_by?: string
  group_source?: StepLayoutGroupSource
  filter_fields?: string[]
  stats_groups?: StepLayoutColumn[]
  source?: string
}

export type StepContextStep = {
  key: string
  title: string
}

export type StepInputColumn = {
  key: string
  label: string
  kind: 'text' | 'number' | 'select'
  required?: boolean
  min_value?: number | null
  max_value?: number | null
  step?: number | null
  default?: unknown
  options?: string[]
  max_length?: number | null
  min_length?: number | null
  pattern?: string | null
  visible_when?: { column: string; value: string } | null
  enabled_when?: { column: string; value: string } | null
}

export type StepInputField = {
  key: string
  label: string
  help_text: string
  kind: 'textarea' | 'text' | 'number' | 'select' | 'multi_select' | 'table' | 'date'
  max_length: number
  required?: boolean
  min_value?: number | null
  max_value?: number | null
  step?: number | null
  default?: unknown
  options?: string[]
  min_rows?: number | null
  max_rows?: number | null
  columns?: StepInputColumn[]
  unique_column?: string | null
  required_option?: string | null
  require_estimated_row?: boolean
  pattern?: string | null
}

export type StepInputValue = string | number | string[] | Record<string, unknown>[]

export function resolveLayoutValue(
  content: Record<string, unknown>,
  section: StepLayoutSection,
): unknown {
  if (!section.source) return content[section.key]
  let current: unknown = content
  for (const part of section.source.split('.')) {
    if (current == null || typeof current !== 'object' || Array.isArray(current)) {
      return undefined
    }
    current = (current as Record<string, unknown>)[part]
  }
  return current
}

export function sectionDomId(key: string): string {
  return key.replace(/_/g, '-')
}

export function prettyToken(value: string): string {
  const pretty = value.replace(/_/g, ' ')
  return pretty.length > 0 ? pretty.charAt(0).toUpperCase() + pretty.slice(1) : pretty
}

export function humanizeFieldLabel(field: string): string {
  const trimmed = field.replace(/_ids$/, '').replace(/_id$/, '').replace(/_refs$/, '')
  const label = trimmed.replace(/_/g, ' ')
  return label.charAt(0).toUpperCase() + label.slice(1)
}

export function humanizeBadgeField(field: string, value: string): string {
  if (value.includes(', ')) {
    const parts = value.split(', ').map((part) => prettyToken(part.trim()))
    return `${humanizeFieldLabel(field)}: ${parts.join(', ')}`
  }
  return `${humanizeFieldLabel(field)}: ${prettyToken(value)}`
}

export function refLabel(prefix: string, index: number): string {
  return `${prefix}-${index}`
}

export function chipValues(value: unknown): string[] {
  if (value == null) return []
  if (Array.isArray(value)) {
    return value.map((item) => (typeof item === 'string' ? item : String(item))).filter((s) => s.trim())
  }
  const text = typeof value === 'string' ? value : String(value)
  return text.trim() ? [text] : []
}
