import type { StepLayoutSection } from '@/lib/stepLayoutTypes'
import { formatClientQuestions } from '@/lib/copyClientQuestions'

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function formatCopyableSectionText(
  section: StepLayoutSection,
  content: Record<string, unknown>,
): string {
  const raw = content[section.key]
  if (section.kind === 'numbered_list') {
    if (!Array.isArray(raw)) return ''
    return raw
      .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      .map((item, index) => `${index + 1}. ${item}`)
      .join('\n\n')
  }
  if (section.kind === 'table' && section.key === 'ambiguities_and_questions') {
    if (!Array.isArray(raw)) return ''
    const rows = raw
      .map((row) => {
        if (!row || typeof row !== 'object') return null
        const o = row as Record<string, unknown>
        return {
          question: asString(o.question),
          why_it_matters: asString(o.why_it_matters),
        }
      })
      .filter((x): x is { question: string; why_it_matters: string } => x !== null)
    return formatClientQuestions(rows)
  }
  if (section.kind === 'list') {
    if (!Array.isArray(raw)) return ''
    return raw.filter((x): x is string => typeof x === 'string').join('\n')
  }
  return ''
}
