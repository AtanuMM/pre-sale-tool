export type AmbiguityQuestionRow = {
  question: string
  why_it_matters: string
}

export function formatClientQuestions(items: AmbiguityQuestionRow[]): string {
  if (items.length === 0) return ''
  return items
    .map((item, index) => {
      const lines = [`${index + 1}. ${item.question}`]
      if (item.why_it_matters.trim()) {
        lines.push(`   Why it matters: ${item.why_it_matters}`)
      }
      return lines.join('\n')
    })
    .join('\n\n')
}
