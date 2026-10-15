import type { StepInputField, StepInputValue } from '@/lib/stepLayoutTypes'

export function defaultInputValues(
  fields: StepInputField[],
): Record<string, StepInputValue> {
  const out: Record<string, StepInputValue> = {}
  for (const field of fields) {
    if (field.kind === 'table') {
      out[field.key] = []
      continue
    }
    if (field.default !== undefined && field.default !== null) {
      out[field.key] = field.default as StepInputValue
    } else if (field.kind === 'multi_select') {
      out[field.key] = field.required_option ? [field.required_option] : []
    } else if (field.kind === 'number' && field.default != null) {
      out[field.key] = Number(field.default)
    } else if (field.kind === 'textarea' || field.kind === 'text' || field.kind === 'select') {
      out[field.key] = (field.default as string | undefined) ?? ''
    }
  }
  return out
}

export function collectStepInputs(
  fields: StepInputField[],
  values: Record<string, StepInputValue>,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const field of fields) {
    const value = values[field.key]
    if (field.kind === 'textarea' || field.kind === 'text' || field.kind === 'select') {
      const text = typeof value === 'string' ? value.trim() : ''
      if (text) payload[field.key] = text
      continue
    }
    if (field.kind === 'number') {
      if (typeof value === 'number' && Number.isFinite(value)) {
        payload[field.key] = value
      }
      continue
    }
    if (field.kind === 'multi_select') {
      if (Array.isArray(value) && value.length > 0) payload[field.key] = value
      continue
    }
    if (field.kind === 'table') {
      if (Array.isArray(value) && value.length > 0) payload[field.key] = value
    }
  }
  return payload
}

export function parseUserInputs(
  raw: unknown,
  fields: StepInputField[],
): Record<string, StepInputValue> {
  const base = defaultInputValues(fields)
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return base
  const record = raw as Record<string, unknown>
  for (const field of fields) {
    if (!(field.key in record)) continue
    const value = record[field.key]
    if (field.kind === 'textarea' || field.kind === 'text' || field.kind === 'select') {
      if (typeof value === 'string') base[field.key] = value
    } else if (field.kind === 'number') {
      if (typeof value === 'number') base[field.key] = value
    } else if (field.kind === 'multi_select') {
      if (Array.isArray(value) && value.every((item) => typeof item === 'string')) {
        base[field.key] = value as string[]
      }
    } else if (field.kind === 'table') {
      if (Array.isArray(value)) {
        base[field.key] = value.filter(
          (row): row is Record<string, unknown> =>
            row != null && typeof row === 'object' && !Array.isArray(row),
        )
      }
    }
  }
  return base
}
