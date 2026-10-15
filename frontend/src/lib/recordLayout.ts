import type { StepLayoutSection } from '@/lib/stepLayoutTypes'

export function asRecordRows(raw: unknown): Record<string, unknown>[] {
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (row): row is Record<string, unknown> => row != null && typeof row === 'object',
  )
}

function scalarValues(value: unknown): string[] {
  if (value == null) return []
  if (Array.isArray(value)) {
    return value
      .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      .map((item) => item.trim())
  }
  if (typeof value === 'string' && value.trim()) return [value.trim()]
  return []
}

export function uniqueFilterValues(
  rows: Record<string, unknown>[],
  field: string,
): string[] {
  const seen = new Set<string>()
  const ordered: string[] = []
  for (const row of rows) {
    for (const value of scalarValues(row[field])) {
      if (!seen.has(value)) {
        seen.add(value)
        ordered.push(value)
      }
    }
  }
  return ordered
}

export function rowMatchesFilters(
  row: Record<string, unknown>,
  filters: Record<string, string>,
): boolean {
  for (const [field, selected] of Object.entries(filters)) {
    if (!selected) continue
    const values = scalarValues(row[field])
    if (!values.includes(selected)) return false
  }
  return true
}

export type RecordGroup = {
  heading: string
  intro: string
  rows: { index: number; row: Record<string, unknown> }[]
}

export function groupRecordRows(
  section: StepLayoutSection,
  content: Record<string, unknown>,
  rows: { index: number; row: Record<string, unknown> }[],
): RecordGroup[] {
  if (!section.group_by || !section.group_source) {
    return [{ heading: '', intro: '', rows }]
  }
  const sourceRaw = content[section.group_source.section]
  const sourceRows = asRecordRows(sourceRaw)
  const order: { name: string; intro: string }[] = []
  const seen = new Set<string>()
  for (const item of sourceRows) {
    const name = String(item[section.group_source.key_field] ?? '').trim()
    if (!name || seen.has(name.toLowerCase())) continue
    seen.add(name.toLowerCase())
    order.push({
      name,
      intro: String(item[section.group_source.intro_field] ?? '').trim(),
    })
  }
  const buckets = new Map<string, { index: number; row: Record<string, unknown> }[]>()
  for (const item of order) buckets.set(item.name, [])
  const extras = new Map<string, { index: number; row: Record<string, unknown> }[]>()
  for (const indexed of rows) {
    const name = String(indexed.row[section.group_by] ?? '').trim() || 'Other'
    const match = order.find((item) => item.name.toLowerCase() === name.toLowerCase())
    if (match) {
      buckets.get(match.name)?.push(indexed)
    } else {
      const list = extras.get(name) ?? []
      list.push(indexed)
      extras.set(name, list)
    }
  }
  const groups: RecordGroup[] = []
  for (const item of order) {
    const grouped = buckets.get(item.name) ?? []
    if (grouped.length > 0) {
      groups.push({ heading: item.name, intro: item.intro, rows: grouped })
    }
  }
  for (const [name, grouped] of extras) {
    groups.push({ heading: name, intro: '', rows: grouped })
  }
  return groups.length > 0 ? groups : [{ heading: '', intro: '', rows }]
}
