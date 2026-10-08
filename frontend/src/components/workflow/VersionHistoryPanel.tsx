import type { StepVersionSummary } from '@/api/steps'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { versionSourceLabel, versionStatusLabel } from '@/lib/stepLabels'
import { stepVersionCanDownload } from '@/lib/stepVersionDownload'
import { formatRelativeTime } from '@/lib/formatRelativeTime'
import { cn } from '@/lib/utils'
import { DownloadIcon, Loader2Icon } from 'lucide-react'

type VersionHistoryPanelProps = {
  versions: StepVersionSummary[]
  selectedId: string | null
  currentVersionId: string | null
  onSelect: (id: string) => void
  canDownload?: boolean
  downloadingVersionId?: string | null
  onDownload?: (version: StepVersionSummary) => void
  className?: string
}

export function VersionHistoryPanel({
  versions,
  selectedId,
  currentVersionId,
  onSelect,
  canDownload = false,
  downloadingVersionId = null,
  onDownload,
  className,
}: VersionHistoryPanelProps) {
  const sorted = [...versions].sort((a, b) => b.version_no - a.version_no)
  return (
    <aside className={cn('space-y-2', className)} aria-label="Version history">
      <h3 className="text-sm font-semibold">Versions</h3>
      <ul className="space-y-2">
        {sorted.map((v) => {
          const selected = v.id === selectedId
          const isCurrent = v.id === currentVersionId
          const showDownload =
            canDownload && stepVersionCanDownload(v.status) && onDownload != null
          const downloading = downloadingVersionId === v.id
          return (
            <li key={v.id}>
              <div
                className={cn(
                  'flex w-full gap-1 rounded-md border border-border',
                  selected && 'ring-1 ring-ring',
                )}
              >
                <Button
                  type="button"
                  variant={selected ? 'secondary' : 'outline'}
                  className="h-auto min-w-0 flex-1 flex-col items-start gap-1 rounded-r-none border-0 px-3 py-2 text-left shadow-none"
                  onClick={() => onSelect(v.id)}
                >
                  <span className="flex w-full flex-wrap items-center gap-2 text-xs">
                    <span className="font-semibold">v{v.version_no}</span>
                    <Badge variant="outline">{versionSourceLabel(v.source)}</Badge>
                    <Badge variant="secondary">{versionStatusLabel(v.status)}</Badge>
                    {isCurrent ? (
                      <Badge variant="default" className="text-[10px]">
                        Current
                      </Badge>
                    ) : null}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {v.created_by_name ?? 'Unknown'} · {formatRelativeTime(v.created_at)}
                  </span>
                  {v.tokens_in != null || v.tokens_out != null ? (
                    <span className="text-[10px] text-muted-foreground">
                      Tokens in {v.tokens_in ?? '—'} · out {v.tokens_out ?? '—'}
                    </span>
                  ) : null}
                </Button>
                {showDownload ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    className="shrink-0 self-stretch rounded-l-none border-0 border-l border-border"
                    aria-label={`Download version ${v.version_no}`}
                    disabled={downloading}
                    onClick={(event) => {
                      event.stopPropagation()
                      onDownload(v)
                    }}
                  >
                    {downloading ? (
                      <Loader2Icon className="size-4 animate-spin" aria-hidden />
                    ) : (
                      <DownloadIcon className="size-4" aria-hidden />
                    )}
                  </Button>
                ) : null}
              </div>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
