import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type PlainTextBlockProps = {
  text: string
  collapsedLines?: number
  className?: string
}

/** Renders untrusted text as plain text only (no HTML/markdown/links). */
export function PlainTextBlock({
  text,
  collapsedLines = 8,
  className,
}: PlainTextBlockProps) {
  const [expanded, setExpanded] = useState(false)
  const lines = text.split('\n')
  const needsCollapse = lines.length > collapsedLines
  const visible = expanded || !needsCollapse ? text : lines.slice(0, collapsedLines).join('\n')

  return (
    <div className={cn('space-y-2', className)}>
      <pre className="whitespace-pre-wrap break-words font-sans text-sm text-foreground">{visible}</pre>
      {needsCollapse ? (
        <Button type="button" variant="ghost" size="sm" onClick={() => setExpanded((v) => !v)}>
          {expanded ? 'Show less' : 'Show more'}
        </Button>
      ) : null}
    </div>
  )
}
