import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { prettyToken } from '@/lib/stepLayoutTypes'
import { cn } from '@/lib/utils'

type FormSelectProps = {
  id?: string
  value: string
  onChange: (value: string) => void
  options: readonly string[]
  disabled?: boolean
  placeholder?: string
  triggerClassName?: string
  'aria-label'?: string
}

export function FormSelect({
  id,
  value,
  onChange,
  options,
  disabled,
  placeholder,
  triggerClassName,
  'aria-label': ariaLabel,
}: FormSelectProps) {
  return (
    <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger id={id} className={cn('w-full', triggerClassName)} aria-label={ariaLabel}>
        <SelectValue placeholder={placeholder ?? 'Select…'} />
      </SelectTrigger>
      <SelectContent>
        {options.map((opt) => (
          <SelectItem key={opt} value={opt}>
            {prettyToken(opt)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** Radix select value for an optional filter (maps “All” ↔ empty string). */
export const FILTER_ALL_VALUE = '__all__'

type FilterSelectProps = {
  id?: string
  value: string
  onChange: (value: string) => void
  options: readonly string[]
  triggerClassName?: string
}

export function FilterSelect({
  id,
  value,
  onChange,
  options,
  triggerClassName,
}: FilterSelectProps) {
  const radixValue = value === '' ? FILTER_ALL_VALUE : value
  return (
    <Select
      value={radixValue}
      onValueChange={(next) => onChange(next === FILTER_ALL_VALUE ? '' : next)}
    >
      <SelectTrigger
        id={id}
        className={cn('min-w-[8rem]', triggerClassName)}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={FILTER_ALL_VALUE}>All</SelectItem>
        {options.map((opt) => (
          <SelectItem key={opt} value={opt}>
            {prettyToken(opt)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
