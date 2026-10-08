import { useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PlainTextBlock } from '@/components/projects/PlainTextBlock'
import { copyTextToClipboard } from '@/lib/copyToClipboard'
import { formatCopyableSectionText } from '@/lib/formatCopyableSection'
import {
  humanizeBadgeField,
  sectionDomId,
  type StepLayoutSection,
} from '@/lib/stepLayoutTypes'
import { cn } from '@/lib/utils'

type GenericStepViewerProps = {
  layout: StepLayoutSection[]
  content: Record<string, unknown>
  className?: string
}

function cellText(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  return String(value)
}

export function GenericStepViewer({ layout, content, className }: GenericStepViewerProps) {
  const [clipboardFallback, setClipboardFallback] = useState<string | null>(null)
  const [copySectionKey, setCopySectionKey] = useState<string | null>(null)
  const fallbackRef = useRef<HTMLTextAreaElement>(null)

  const sections = useMemo(() => layout.filter((s) => s.key in content), [layout, content])

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const onCopySection = async (section: StepLayoutSection) => {
    const text = formatCopyableSectionText(section, content)
    if (!text) {
      toast.message('Nothing to copy')
      return
    }
    const result = await copyTextToClipboard(text)
    if (result.ok) {
      toast.success('Copied')
      setClipboardFallback(null)
      setCopySectionKey(null)
      return
    }
    toast.error('Could not copy automatically')
    setCopySectionKey(section.key)
    setClipboardFallback(text)
    requestAnimationFrame(() => {
      fallbackRef.current?.focus()
      fallbackRef.current?.select()
    })
  }

  return (
    <div className={cn('flex flex-col gap-6 lg:flex-row', className)}>
      <nav
        aria-label="Section index"
        className="flex shrink-0 flex-wrap gap-2 lg:w-44 lg:flex-col lg:gap-1"
      >
        {layout.map((s) => (
          <Button
            key={s.key}
            type="button"
            variant="ghost"
            size="sm"
            className="h-auto justify-start px-2 py-1 text-xs lg:w-full"
            onClick={() => scrollTo(sectionDomId(s.key))}
          >
            {s.title}
          </Button>
        ))}
      </nav>
      <div className="min-w-0 flex-1 space-y-4">
        {sections.map((section) => (
          <Card key={section.key} id={sectionDomId(section.key)}>
            <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-base">{section.title}</CardTitle>
              {section.copyable ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => void onCopySection(section)}
                >
                  Copy for client
                </Button>
              ) : null}
            </CardHeader>
            <CardContent>{renderSection(section, content[section.key])}</CardContent>
          </Card>
        ))}
        {copySectionKey && clipboardFallback ? (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">Select and copy manually:</p>
            <textarea
              ref={fallbackRef}
              readOnly
              className="h-32 w-full rounded-md border border-border bg-muted px-3 py-2 font-mono text-xs"
              value={clipboardFallback}
              aria-label="Copy fallback"
            />
          </div>
        ) : null}
      </div>
    </div>
  )
}

function renderSection(section: StepLayoutSection, raw: unknown) {
  if (section.kind === 'text') {
    return <PlainTextBlock text={cellText(raw)} />
  }
  if (section.kind === 'list' || section.kind === 'numbered_list') {
    const items = Array.isArray(raw)
      ? raw.filter((x): x is string => typeof x === 'string')
      : []
    if (items.length === 0) {
      return <p className="text-sm text-muted-foreground">None listed.</p>
    }
    if (section.kind === 'numbered_list') {
      return (
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          {items.map((item) => (
            <li key={item} className="whitespace-pre-wrap break-words">
              {item}
            </li>
          ))}
        </ol>
      )
    }
    return (
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {items.map((item) => (
          <li key={item} className="whitespace-pre-wrap break-words">
            {item}
          </li>
        ))}
      </ul>
    )
  }
  if (section.kind === 'table') {
    const rows = Array.isArray(raw)
      ? raw.filter((x): x is Record<string, unknown> => x != null && typeof x === 'object')
      : []
    const cols = section.columns ?? []
    if (rows.length === 0 || cols.length === 0) {
      return <p className="text-sm text-muted-foreground">None listed.</p>
    }
    return (
      <div className="overflow-x-auto">
        <table className="w-full min-w-[20rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              {cols.map((c) => (
                <th key={c.key} className="py-2 pr-3 font-medium">
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={idx} className="border-b border-border/60">
                {cols.map((c) => (
                  <td
                    key={c.key}
                    className="py-2 pr-3 align-top whitespace-pre-wrap break-words"
                  >
                    {cellText(row[c.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  if (section.kind === 'records') {
    const rows = Array.isArray(raw)
      ? raw.filter((x): x is Record<string, unknown> => x != null && typeof x === 'object')
      : []
    const fields = section.record_fields ?? []
    if (rows.length === 0) {
      return <p className="text-sm text-muted-foreground">None listed.</p>
    }
    return (
      <div className="space-y-3">
        {rows.map((row, idx) => (
          <div key={idx} className="rounded-lg border border-border p-3 text-sm space-y-2">
            {section.badge_fields && section.badge_fields.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {section.badge_fields.map((bf) => {
                  const val = cellText(row[bf])
                  if (!val) return null
                  return (
                    <Badge key={bf} variant="outline">
                      {humanizeBadgeField(bf, val)}
                    </Badge>
                  )
                })}
              </div>
            ) : null}
            {fields.map((f) => {
              const val = cellText(row[f.key])
              if (!val) return null
              return (
                <div key={f.key}>
                  <p className="text-xs font-medium text-muted-foreground">{f.header}</p>
                  <p className="whitespace-pre-wrap break-words">{val}</p>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    )
  }
  return null
}
