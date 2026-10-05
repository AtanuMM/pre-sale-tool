import type { LucideIcon } from 'lucide-react'

import { IconChip, type IconChipTone } from '@/components/layout/IconChip'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

type StatCardProps = {
  label: string
  value: string | number
  icon: LucideIcon
  tone?: IconChipTone
  className?: string
}

export function StatCard({ label, value, icon, tone = 'sky', className }: StatCardProps) {
  return (
    <Card className={cn('gap-0 py-0 shadow-card', className)}>
      <CardContent className="flex items-center gap-4 py-5">
        <IconChip icon={icon} tone={tone} />
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold tabular-nums tracking-tight text-foreground">
            {value}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
