import type { ExtractionStatus } from '@/api/projects'
import { Badge } from '@/components/ui/badge'
import { extractionStatusLabel } from '@/lib/projectLabels'
import { cn } from '@/lib/utils'

type ExtractionBadgeProps = {
  status: ExtractionStatus
  extractedCharCount: number
  showEmptyHint?: boolean
  className?: string
}

export function ExtractionBadge({
  status,
  extractedCharCount,
  showEmptyHint = true,
  className,
}: ExtractionBadgeProps) {
  const variant =
    status === 'ok' ? 'default' : status === 'truncated' ? 'secondary' : 'outline'

  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <Badge variant={variant} className="w-fit">
        {extractionStatusLabel(status)}
        {status !== 'empty' ? ` · ${extractedCharCount.toLocaleString()} chars` : ''}
      </Badge>
      {showEmptyHint && status === 'empty' ? (
        <p className="text-xs text-muted-foreground">
          No text could be read from this file (scanned PDFs are not supported). The AI will not
          see this attachment.
        </p>
      ) : null}
    </div>
  )
}
