import type { LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

export type IconChipTone = 'teal' | 'amber' | 'rose' | 'sky' | 'primary'

const toneClasses: Record<IconChipTone, string> = {
  teal: 'bg-chip-teal text-chip-teal-foreground',
  amber: 'bg-chip-amber text-chip-amber-foreground',
  rose: 'bg-chip-rose text-chip-rose-foreground',
  sky: 'bg-chip-sky text-chip-sky-foreground',
  primary: 'bg-primary text-primary-foreground',
}

type IconChipProps = {
  icon: LucideIcon
  tone?: IconChipTone
  className?: string
  size?: 'sm' | 'md'
}

export function IconChip({ icon: Icon, tone = 'primary', className, size = 'md' }: IconChipProps) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full',
        toneClasses[tone],
        size === 'sm' ? 'size-8' : 'size-10',
        className,
      )}
      aria-hidden
    >
      <Icon className={size === 'sm' ? 'size-4' : 'size-5'} />
    </span>
  )
}
