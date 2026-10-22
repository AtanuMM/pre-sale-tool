import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { TYPICAL_TEAM_ROWS } from '@/lib/typicalTeam'
import { FormSelect } from '@/components/workflow/FormSelect'
import {
  prettyToken,
  type StepInputColumn,
  type StepInputField,
  type StepInputValue,
} from '@/lib/stepLayoutTypes'

type StepInputFieldsProps = {
  fields: StepInputField[]
  values: Record<string, StepInputValue>
  onChange: (key: string, value: StepInputValue) => void
  disabled?: boolean
}

function emptyRow(columns: StepInputColumn[]): Record<string, unknown> {
  const row: Record<string, unknown> = {}
  for (const col of columns) {
    if (col.default !== undefined) row[col.key] = col.default
  }
  return row
}

function columnVisible(col: StepInputColumn, row: Record<string, unknown>): boolean {
  if (!col.visible_when) return true
  return String(row[col.visible_when.column] ?? '') === col.visible_when.value
}

function columnEnabled(col: StepInputColumn, row: Record<string, unknown>): boolean {
  if (!col.enabled_when) return true
  return String(row[col.enabled_when.column] ?? '') === col.enabled_when.value
}

export function StepInputFields({
  fields,
  values,
  onChange,
  disabled = false,
}: StepInputFieldsProps) {
  if (fields.length === 0) return null
  return (
    <div className="space-y-6">
      {fields.map((field) => {
        if (field.kind === 'date') {
          const value = typeof values[field.key] === 'string' ? (values[field.key] as string) : ''
          return (
            <div key={field.key} className="space-y-2">
              <Label htmlFor={field.key}>{field.label}</Label>
              <Input
                id={field.key}
                type="date"
                value={value}
                onChange={(event) => onChange(field.key, event.target.value)}
                disabled={disabled}
                aria-describedby={`${field.key}-help`}
              />
              <p id={`${field.key}-help`} className="text-xs text-muted-foreground">
                {field.help_text}
              </p>
            </div>
          )
        }
        if (field.kind === 'textarea' || field.kind === 'text') {
          const value = typeof values[field.key] === 'string' ? (values[field.key] as string) : ''
          const helpId = `${field.key}-help`
          const countId = `${field.key}-count`
          return (
            <div key={field.key} className="space-y-2">
              <Label htmlFor={field.key}>{field.label}</Label>
              {field.kind === 'textarea' ? (
                <Textarea
                  id={field.key}
                  value={value}
                  onChange={(event) => onChange(field.key, event.target.value)}
                  rows={6}
                  disabled={disabled}
                  maxLength={field.max_length}
                  aria-describedby={`${helpId} ${countId}`}
                />
              ) : (
                <Input
                  id={field.key}
                  type={field.pattern === '^\\d{4}-\\d{2}-\\d{2}$' ? 'date' : 'text'}
                  value={value}
                  onChange={(event) => onChange(field.key, event.target.value)}
                  disabled={disabled}
                  maxLength={field.max_length}
                  aria-describedby={helpId}
                />
              )}
              <p id={helpId} className="text-xs text-muted-foreground">
                {field.help_text}
              </p>
              {field.kind === 'textarea' ? (
                <p id={countId} className="text-xs text-muted-foreground">
                  {value.length} / {field.max_length} characters
                </p>
              ) : null}
            </div>
          )
        }
        if (field.kind === 'number') {
          const raw = values[field.key]
          const value = typeof raw === 'number' ? String(raw) : ''
          return (
            <div key={field.key} className="space-y-2">
              <Label htmlFor={field.key}>{field.label}</Label>
              <Input
                id={field.key}
                type="number"
                value={value}
                min={field.min_value ?? undefined}
                max={field.max_value ?? undefined}
                step={field.step ?? undefined}
                disabled={disabled}
                onChange={(event) => {
                  const next = event.target.value
                  onChange(field.key, next === '' ? '' : Number(next))
                }}
              />
              <p className="text-xs text-muted-foreground">{field.help_text}</p>
            </div>
          )
        }
        if (field.kind === 'select') {
          const value = typeof values[field.key] === 'string' ? (values[field.key] as string) : ''
          return (
            <div key={field.key} className="space-y-2">
              <Label htmlFor={field.key}>{field.label}</Label>
              <FormSelect
                id={field.key}
                value={value}
                disabled={disabled}
                options={field.options ?? []}
                onChange={(next) => onChange(field.key, next)}
              />
              <p className="text-xs text-muted-foreground">{field.help_text}</p>
            </div>
          )
        }
        if (field.kind === 'multi_select') {
          const selected = Array.isArray(values[field.key])
            ? (values[field.key] as string[])
            : []
          return (
            <div key={field.key} className="space-y-2">
              <p className="text-sm font-medium">{field.label}</p>
              <div className="flex flex-wrap gap-3">
                {(field.options ?? []).map((option) => {
                  const checked = selected.includes(option)
                  const locked = option === field.required_option
                  const id = `${field.key}-${option}`
                  return (
                    <label key={option} htmlFor={id} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        id={id}
                        checked={checked}
                        disabled={disabled || locked}
                        onCheckedChange={(state) => {
                          if (locked) return
                          const next = state
                            ? [...selected, option]
                            : selected.filter((item) => item !== option)
                          onChange(field.key, next)
                        }}
                      />
                      {prettyToken(option)}
                    </label>
                  )
                })}
              </div>
              <p className="text-xs text-muted-foreground">{field.help_text}</p>
            </div>
          )
        }
        if (field.kind === 'table') {
          const rows = Array.isArray(values[field.key])
            ? (values[field.key] as Record<string, unknown>[])
            : []
          const columns = field.columns ?? []
          const headcount = rows.reduce((sum, row) => {
            const n = row.headcount
            return sum + (typeof n === 'number' ? n : 0)
          }, 0)
          return (
            <div key={field.key} className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label>{field.label}</Label>
                {field.key === 'team' ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={disabled}
                    onClick={() => onChange(field.key, TYPICAL_TEAM_ROWS.map((row) => ({ ...row })))}
                  >
                    Use a typical team
                  </Button>
                ) : null}
              </div>
              {field.key === 'team' ? (
                <p className="text-xs text-muted-foreground">
                  Typical team fills example rows you can edit. They are examples, not recommendations.
                </p>
              ) : null}
              <div className="overflow-x-auto">
                <table className="w-full min-w-[40rem] border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-border text-left">
                      {columns.map((col) => (
                        <th key={col.key} className="py-2 pr-2 font-medium">
                          {col.label}
                        </th>
                      ))}
                      <th className="py-2 font-medium"> </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={index} className="border-b border-border/60">
                        {columns.map((col) => {
                          if (!columnVisible(col, row)) {
                            return <td key={col.key} className="py-1 pr-2" />
                          }
                          const cellId = `${field.key}-${index}-${col.key}`
                          const raw = row[col.key]
                          if (col.kind === 'select') {
                            return (
                              <td key={col.key} className="py-1 pr-2">
                                <FormSelect
                                  id={cellId}
                                  aria-label={`${col.label} row ${index + 1}`}
                                  triggerClassName="h-8 min-w-[8rem]"
                                  disabled={disabled || !columnEnabled(col, row)}
                                  value={typeof raw === 'string' ? raw : String(col.default ?? '')}
                                  options={col.options ?? []}
                                  onChange={(nextValue) => {
                                    const next = rows.map((item, i) => {
                                      if (i !== index) return item
                                      const updated = { ...item, [col.key]: nextValue }
                                      if (col.key === 'discipline' && nextValue !== 'development') {
                                        updated.ai_gain_pct = 0
                                      }
                                      return updated
                                    })
                                    onChange(field.key, next)
                                  }}
                                />
                              </td>
                            )
                          }
                          if (col.kind === 'number') {
                            const enabled = columnEnabled(col, row)
                            const warnAi =
                              col.key === 'ai_gain_pct' && typeof raw === 'number' && raw > 50
                            return (
                              <td key={col.key} className="py-1 pr-2">
                                <Input
                                  id={cellId}
                                  type="number"
                                  className="h-8"
                                  aria-label={`${col.label} row ${index + 1}`}
                                  disabled={disabled || !enabled}
                                  min={col.min_value ?? undefined}
                                  max={col.max_value ?? undefined}
                                  step={col.step ?? undefined}
                                  value={typeof raw === 'number' ? String(raw) : ''}
                                  aria-invalid={warnAi || undefined}
                                  onChange={(event) => {
                                    const text = event.target.value
                                    const next = rows.map((item, i) =>
                                      i === index
                                        ? {
                                            ...item,
                                            [col.key]: text === '' ? '' : Number(text),
                                          }
                                        : item,
                                    )
                                    onChange(field.key, next)
                                  }}
                                />
                                {col.key === 'ai_gain_pct' && !enabled ? (
                                  <p className="text-[10px] text-muted-foreground">
                                    AI gain applies only to development roles
                                  </p>
                                ) : null}
                                {warnAi ? (
                                  <p className="text-[10px] text-muted-foreground">
                                    AI gain above 50% is unusually high
                                  </p>
                                ) : null}
                              </td>
                            )
                          }
                          return (
                            <td key={col.key} className="py-1 pr-2">
                              <Input
                                id={cellId}
                                className="h-8"
                                aria-label={`${col.label} row ${index + 1}`}
                                disabled={disabled}
                                maxLength={col.max_length ?? undefined}
                                value={typeof raw === 'string' ? raw : ''}
                                onChange={(event) => {
                                  const next = rows.map((item, i) =>
                                    i === index ? { ...item, [col.key]: event.target.value } : item,
                                  )
                                  onChange(field.key, next)
                                }}
                              />
                            </td>
                          )
                        })}
                        <td className="py-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={disabled || rows.length <= (field.min_rows ?? 0)}
                            onClick={() =>
                              onChange(
                                field.key,
                                rows.filter((_, i) => i !== index),
                              )
                            }
                          >
                            Remove
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={disabled || rows.length >= (field.max_rows ?? 15)}
                  onClick={() => onChange(field.key, [...rows, emptyRow(columns)])}
                >
                  Add row
                </Button>
                <p className="text-xs text-muted-foreground">Headcount total: {headcount}</p>
              </div>
              <p className="text-xs text-muted-foreground">{field.help_text}</p>
            </div>
          )
        }
        return null
      })}
    </div>
  )
}
