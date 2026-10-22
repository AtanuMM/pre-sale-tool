import { useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FilterSelect } from '@/components/workflow/FormSelect'
import { PlainTextBlock } from '@/components/projects/PlainTextBlock'
import { copyTextToClipboard } from '@/lib/copyToClipboard'
import { formatCopyableSectionText } from '@/lib/formatCopyableSection'
import {
  asRecordRows,
  groupRecordRows,
  rowMatchesFilters,
  uniqueFilterValues,
} from '@/lib/recordLayout'
import {
  chipValues,
  humanizeBadgeField,
  humanizeFieldLabel,
  prettyToken,
  refLabel,
  resolveLayoutValue,
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
  if (Array.isArray(value)) {
    return value.map((item) => cellText(item)).filter(Boolean).join(', ')
  }
  return String(value)
}

export function GenericStepViewer({ layout, content, className }: GenericStepViewerProps) {
  const [clipboardFallback, setClipboardFallback] = useState<string | null>(null)
  const [copySectionKey, setCopySectionKey] = useState<string | null>(null)
  const fallbackRef = useRef<HTMLTextAreaElement>(null)

  const sections = useMemo(
    () =>
      layout.filter((s) => {
        const raw = resolveLayoutValue(content, s)
        if (s.kind === 'warning_strip') {
          return (
            Array.isArray(raw) &&
            raw.some(
              (item) =>
                item != null &&
                typeof item === 'object' &&
                typeof (item as Record<string, unknown>).count === 'number' &&
                Number((item as Record<string, unknown>).count) > 0,
            )
          )
        }
        if (s.kind === 'open_items') {
          return raw != null && typeof raw === 'object'
        }
        return raw !== undefined && raw !== null
      }),
    [layout, content],
  )

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
            <CardContent>
              {section.kind === 'records' ? (
                <RecordsSection section={section} content={content} />
              ) : (
                renderSection(section, resolveLayoutValue(content, section), content)
              )}
            </CardContent>
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

function Chip({ children }: { children: string }) {
  return (
    <Badge variant="outline" className="font-mono text-[0.7rem]">
      {children}
    </Badge>
  )
}

function renderSection(
  section: StepLayoutSection,
  raw: unknown,
  content: Record<string, unknown>,
) {
  if (section.kind === 'health_panel') {
    const health = raw as Record<string, unknown> | null
    if (!health) return <p className="text-sm text-muted-foreground">No health data.</p>
    const rows = health.health_rows
    if (Array.isArray(rows) && rows.length > 0) {
      return (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="p-2">Check</th>
                <th className="p-2">Value</th>
                <th className="p-2">Threshold</th>
                <th className="p-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {(rows as Record<string, unknown>[]).map((row, index) => (
                <tr key={index} className="border-b border-border/60">
                  <td className="p-2">{cellText(row.label)}</td>
                  <td className="p-2">{cellText(row.value)}</td>
                  <td className="p-2">{cellText(row.threshold)}</td>
                  <td className="p-2">{cellText(row.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }
    return (
      <div className="grid gap-2 text-sm sm:grid-cols-2">
        <p>Requirements per feature: <strong>{String(health.requirements_per_feature ?? '—')}</strong></p>
        <p>Features covered: <strong>{String(health.features_covered_pct ?? '—')}%</strong></p>
        <p>Basis (stated / derived / proposed):{' '}
          <strong>{String(health.basis_stated ?? 0)} / {String(health.basis_derived ?? 0)} / {String(health.basis_proposed ?? 0)}</strong>
        </p>
        <p>Approx. pages: <strong>{String(health.approx_pages ?? '—')}</strong> (approximate)</p>
        <p>Weak-language warnings: <strong>{String(health.weak_language_warnings ?? 0)}</strong></p>
        <p>Placeholders: <strong>{String(health.placeholder_count ?? 0)}</strong></p>
      </div>
    )
  }
  if (section.kind === 'diagram') {
    const versionId = typeof content.version_id === 'string' ? content.version_id : null
    const diagramKey =
      section.key === 'context_diagram'
        ? 'context'
        : section.key === 'architecture_diagram'
          ? 'architecture'
          : section.key === 'deployment_diagram'
            ? 'deployment'
            : 'context'
    if (!versionId) {
      return <p className="text-sm text-muted-foreground">Diagram preview available after generation.</p>
    }
    const src = `/api/step-versions/${versionId}/diagrams/${diagramKey}?format=png`
    return (
      <figure className="space-y-2">
        <img src={src} alt={section.title} className="mx-auto max-w-full rounded-md border border-border" />
        <figcaption className="text-center text-xs text-muted-foreground">{section.title}</figcaption>
      </figure>
    )
  }
  if (section.kind === 'requirement_table') {
    const rows = Array.isArray(raw) ? (raw as Record<string, unknown>[]) : []
    if (rows.length === 0) return <p className="text-sm text-muted-foreground">No requirements.</p>
    return (
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="p-2">ID</th>
              <th className="p-2">Requirement</th>
              <th className="p-2">Priority</th>
              <th className="p-2">Basis</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 200).map((row) => (
              <tr key={String(row.id)} className="border-b border-border/60 align-top">
                <td className="p-2 font-mono text-xs">{cellText(row.id)}</td>
                <td className="p-2">{cellText(row.statement)}</td>
                <td className="p-2">{cellText(row.priority)}</td>
                <td className="p-2">{cellText(row.basis)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length > 200 ? (
          <p className="mt-2 text-xs text-muted-foreground">Showing first 200 of {rows.length} requirements.</p>
        ) : null}
      </div>
    )
  }
  if (section.kind === 'text' || section.kind === 'method_note') {
    return <PlainTextBlock text={cellText(raw)} />
  }
  if (section.kind === 'computed_cards') {
    const items = Array.isArray(raw)
      ? raw.filter((item): item is Record<string, unknown> => item != null && typeof item === 'object')
      : []
    if (items.length === 0) {
      return <p className="text-sm text-muted-foreground">No totals.</p>
    }
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item, index) => (
          <div key={String(item.key ?? index)} className="rounded-lg border border-border p-3">
            <p className="text-xs text-muted-foreground">{cellText(item.label)}</p>
            <p className="mt-1 text-lg font-semibold">{cellText(item.value)}</p>
          </div>
        ))}
      </div>
    )
  }
  if (section.kind === 'open_items') {
    const viewer = raw as Record<string, unknown> | null
    const placeholders = Array.isArray(viewer?.placeholders)
      ? (viewer?.placeholders as Record<string, unknown>[])
      : []
    const warnings = Array.isArray(viewer?.numeric_claim_warnings)
      ? (viewer?.numeric_claim_warnings as Record<string, unknown>[])
      : []
    return (
      <div className="space-y-3 text-sm">
        <p>
          Placeholders: <strong>{String(viewer?.placeholder_count ?? 0)}</strong>
        </p>
        {placeholders.length > 0 ? (
          <ul className="list-disc space-y-1 pl-5">
            {placeholders.map((item, index) => (
              <li key={String(item.placeholder_id ?? index)}>
                {cellText(item.label)} <span className="text-muted-foreground">({cellText(item.location)})</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">No placeholders recorded.</p>
        )}
        {warnings.length > 0 ? (
          <div>
            <p className="font-medium">Check this figure</p>
            <ul className="list-disc space-y-1 pl-5">
              {warnings.map((item, index) => (
                <li key={String(item.path ?? index)}>
                  {cellText(item.label)}: {cellText(item.snippet)}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    )
  }
  if (section.kind === 'standard_terms') {
    const terms = raw as Record<string, unknown> | null
    const version = cellText(terms?.version)
    const blocks = ['acceptance', 'change_control', 'governance', 'warranty', 'legal', 'payment']
    return (
      <div className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          Standard terms v{version} (review with your legal counsel)
        </p>
        {blocks.map((key) => {
          const block = terms?.[key] as Record<string, unknown> | undefined
          if (!block) return null
          const paragraphs = Array.isArray(block.paragraphs) ? (block.paragraphs as string[]) : []
          return (
            <div key={key}>
              <p className="font-medium">{cellText(block.title)}</p>
              {paragraphs.map((p, index) => (
                <p key={index} className="mt-1 whitespace-pre-wrap break-words">
                  {p}
                </p>
              ))}
            </div>
          )
        })}
      </div>
    )
  }
  if (section.kind === 'rich_text') {
    const text = cellText(raw)
    if (!text) return <p className="text-sm text-muted-foreground">None.</p>
    const parts = text.split(/(\[TBC:[^\]]+\])/g)
    return (
      <p className="whitespace-pre-wrap break-words text-sm">
        {parts.map((part, index) =>
          part.startsWith('[TBC:') ? (
            <strong key={index}>{part}</strong>
          ) : (
            <span key={index}>{part}</span>
          ),
        )}
      </p>
    )
  }
  if (section.kind === 'warning_strip') {
    const items = Array.isArray(raw)
      ? raw.filter((item): item is Record<string, unknown> => item != null && typeof item === 'object')
      : []
    return (
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {items.map((item, index) => (
          <li key={String(item.code ?? index)}>
            {cellText(item.label)}: {cellText(item.count)}
          </li>
        ))}
      </ul>
    )
  }
  if (section.kind === 'computed_table') {
    return <ComputedTableSection section={section} raw={raw} />
  }
  if (section.kind === 'stats') {
    return <StatsStrip section={section} raw={raw} />
  }
  if (section.kind === 'list' || section.kind === 'numbered_list') {
    const items = Array.isArray(raw)
      ? raw.filter((x): x is string => typeof x === 'string')
      : []
    if (items.length === 0) {
      return <p className="text-sm text-muted-foreground">None listed.</p>
    }
    const ListTag = section.kind === 'numbered_list' ? 'ol' : 'ul'
    const listClass =
      section.kind === 'numbered_list'
        ? 'list-decimal space-y-1 pl-5 text-sm'
        : 'list-disc space-y-1 pl-5 text-sm'
    return (
      <ListTag className={listClass}>
        {items.map((item, index) => (
          <li key={`${index}-${item}`} className="whitespace-pre-wrap break-words">
            {section.ref_prefix ? (
              <span className="mr-2 inline-flex align-middle">
                <Chip>{refLabel(section.ref_prefix, index + 1)}</Chip>
              </span>
            ) : null}
            {item}
          </li>
        ))}
      </ListTag>
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
              {section.ref_prefix ? (
                <th className="py-2 pr-3 font-medium">Ref</th>
              ) : null}
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
                {section.ref_prefix ? (
                  <td className="py-2 pr-3 align-top">
                    <Chip>{refLabel(section.ref_prefix, idx + 1)}</Chip>
                  </td>
                ) : null}
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
  return null
}

function ComputedTableSection({
  section,
  raw,
}: {
  section: StepLayoutSection
  raw: unknown
}) {
  const allRows = Array.isArray(raw)
    ? raw.filter((row): row is Record<string, unknown> => row != null && typeof row === 'object')
    : []
  const filterFields = section.filter_fields ?? []
  const [filters, setFilters] = useState<Record<string, string>>({})
  const cols =
    section.columns && section.columns.length > 0
      ? section.columns
      : allRows[0]
        ? Object.keys(allRows[0])
            .filter((key) => key !== 'per_role')
            .map((key) => ({ key, header: prettyToken(key) }))
        : []
  const filtered = allRows.filter((row) => {
    return filterFields.every((field) => {
      const selected = filters[field]
      if (!selected) return true
      return cellText(row[field]) === selected
    })
  })
  if (allRows.length === 0 || cols.length === 0) {
    return <p className="text-sm text-muted-foreground">None listed.</p>
  }
  return (
    <div className="space-y-3">
      {filterFields.length > 0 ? (
        <div className="flex flex-wrap gap-3">
          {filterFields.map((field) => {
            const options = Array.from(
              new Set(allRows.map((row) => cellText(row[field])).filter(Boolean)),
            )
            const selectId = `${section.key}-filter-${field}`
            return (
              <div key={field} className="space-y-1">
                <label htmlFor={selectId} className="text-xs font-medium">
                  {humanizeFieldLabel(field)}
                </label>
                <FilterSelect
                  id={selectId}
                  value={filters[field] ?? ''}
                  options={options}
                  triggerClassName="h-9"
                  onChange={(next) =>
                    setFilters((prev) => ({ ...prev, [field]: next }))
                  }
                />
              </div>
            )
          })}
          <p className="self-end text-xs text-muted-foreground" aria-live="polite">
            Showing {filtered.length} of {allRows.length}
          </p>
        </div>
      ) : null}
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
            {filtered.map((row, idx) => (
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
    </div>
  )
}

function StatsStrip({ section, raw }: { section: StepLayoutSection; raw: unknown }) {
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) {
    return <p className="text-sm text-muted-foreground">No totals.</p>
  }
  const data = raw as Record<string, unknown>
  const groups = section.stats_groups ?? []
  if (groups.length === 0) {
    return <p className="text-sm text-muted-foreground">No totals.</p>
  }
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm" role="status">
      {groups.map((group) => {
        const mapping = data[group.key]
        if (mapping == null || typeof mapping !== 'object' || Array.isArray(mapping)) {
          return null
        }
        const entries = Object.entries(mapping as Record<string, unknown>)
        if (entries.length === 0) return null
        return (
          <p key={group.key}>
            <span className="font-medium">{group.header}: </span>
            {entries
              .map(([key, count]) => `${prettyToken(key)} ${String(count)}`)
              .join(', ')}
          </p>
        )
      })}
    </div>
  )
}

function RecordsSection({
  section,
  content,
}: {
  section: StepLayoutSection
  content: Record<string, unknown>
}) {
  const allRows = asRecordRows(content[section.key]).map((row, index) => ({
    index: index + 1,
    row,
  }))
  const filterFields = section.filter_fields ?? []
  const [filters, setFilters] = useState<Record<string, string>>({})
  const filtered = allRows.filter(({ row }) => rowMatchesFilters(row, filters))
  const groups = groupRecordRows(section, content, filtered)

  if (allRows.length === 0) {
    return <p className="text-sm text-muted-foreground">None listed.</p>
  }

  return (
    <div className="space-y-4">
      {filterFields.length > 0 ? (
        <div className="flex flex-wrap gap-3">
          {filterFields.map((field) => {
            const options = uniqueFilterValues(
              allRows.map((item) => item.row),
              field,
            )
            const selectId = `${section.key}-filter-${field}`
            return (
              <div key={field} className="space-y-1">
                <label htmlFor={selectId} className="text-xs font-medium">
                  {humanizeFieldLabel(field)}
                </label>
                <FilterSelect
                  id={selectId}
                  value={filters[field] ?? ''}
                  options={options}
                  triggerClassName="h-9"
                  onChange={(next) =>
                    setFilters((prev) => ({ ...prev, [field]: next }))
                  }
                />
              </div>
            )
          })}
          <p className="self-end text-xs text-muted-foreground" aria-live="polite">
            Showing {filtered.length} of {allRows.length}
          </p>
        </div>
      ) : null}
      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">No items match the filters.</p>
      ) : (
        groups.map((group) => (
          <div key={group.heading || 'all'} className="space-y-3">
            {group.heading ? (
              <div>
                <h3 className="text-sm font-semibold">{group.heading}</h3>
                {group.intro ? (
                  <p className="mt-1 whitespace-pre-wrap break-words text-sm text-muted-foreground">
                    {group.intro}
                  </p>
                ) : null}
              </div>
            ) : null}
            {group.rows.map(({ index, row }) => (
              <RecordCard key={index} section={section} row={row} index={index} />
            ))}
          </div>
        ))
      )}
    </div>
  )
}

function RecordCard({
  section,
  row,
  index,
}: {
  section: StepLayoutSection
  row: Record<string, unknown>
  index: number
}) {
  const fields = section.record_fields ?? []
  const badges = section.badge_fields ?? []
  const chips: string[] = []
  if (section.ref_prefix) chips.push(refLabel(section.ref_prefix, index))
  if (section.id_field) {
    const idVal = cellText(row[section.id_field])
    if (idVal) chips.push(idVal)
  }
  return (
    <div className="space-y-2 rounded-lg border border-border p-3 text-sm">
      {chips.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {chips.map((chip) => (
            <Chip key={chip}>{chip}</Chip>
          ))}
        </div>
      ) : null}
      {badges.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {badges.map((bf) => {
            const raw = row[bf]
            const val = cellText(raw)
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
      {(section.chip_fields ?? []).map((field) => {
        const values = chipValues(row[field])
        if (values.length === 0) return null
        return (
          <div key={field} className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium text-muted-foreground">
              {humanizeFieldLabel(field)}:
            </p>
            {values.map((value) => (
              <Chip key={value}>{value}</Chip>
            ))}
          </div>
        )
      })}
    </div>
  )
}
