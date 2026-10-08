import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import {
  ArchiveIcon,
  CopyIcon,
  DownloadIcon,
  FileIcon,
  Loader2Icon,
  RotateCcwIcon,
} from 'lucide-react'
import { toast } from 'sonner'

import { ApiError } from '@/api/errors'
import { triggerBrowserDownload } from '@/api/download'
import {
  archiveProject,
  buildFollowUpFormData,
  createFollowUpInput,
  downloadProjectFile,
  getProjectFileText,
  getProjectIntakeLimits,
  getProjectOverview,
  patchProjectSettings,
  restoreProject,
  type FileSummary,
  type InputRecord,
  type ProjectOverview,
} from '@/api/projects'
import { useAuth } from '@/auth/AuthContext'
import { ConfirmDialog } from '@/components/layout/ConfirmDialog'
import { EmptyState } from '@/components/layout/EmptyState'
import { FormSheet } from '@/components/layout/FormSheet'
import { PageHeader } from '@/components/layout/PageHeader'
import { WorkflowCompactStepper } from '@/components/workflow/WorkflowCompactStepper'
import { WorkflowTab } from '@/components/workflow/WorkflowTab'
import { useProjectStepsQuery } from '@/hooks/useProjectStepsQuery'
import { ExtractionBadge } from '@/components/projects/ExtractionBadge'
import { IntakeFields, type IntakeFieldsState } from '@/components/projects/IntakeFields'
import { PlainTextBlock } from '@/components/projects/PlainTextBlock'
import { ProjectStatusBadge } from '@/components/projects/ProjectStatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { formatAbsoluteDateTime, formatRelativeTime } from '@/lib/formatRelativeTime'
import { INPUT_KIND_OPTIONS, shortSha256 } from '@/lib/projectLabels'
import {
  PERMISSION_INPUT_ADD,
  PERMISSION_PROJECT_ARCHIVE,
  PERMISSION_SETTINGS_MANAGE,
} from '@/lib/permissions'
import { timelineActionLabel } from '@/lib/timelineLabels'
import {
  isReceivedAtInFuture,
  localDateTimeInputToIso,
  localDateTimeInputValue,
  validateSelectedFiles,
} from '@/lib/validateIntakeFiles'

type TabId = 'overview' | 'workflow' | 'timeline' | 'settings'

function kindLabel(kind: InputRecord['kind']): string {
  return INPUT_KIND_OPTIONS.find((o) => o.value === kind)?.label ?? kind
}

function AttachmentRow({
  projectId,
  file,
}: {
  projectId: string
  file: FileSummary
}) {
  const [downloading, setDownloading] = useState(false)
  const [textOpen, setTextOpen] = useState(false)
  const textQuery = useQuery({
    queryKey: ['projects', projectId, 'file-text', file.id],
    queryFn: () => getProjectFileText(projectId, file.id),
    enabled: textOpen,
  })

  const onDownload = async () => {
    setDownloading(true)
    try {
      const { blob, filename } = await downloadProjectFile(
        projectId,
        file.id,
        file.original_name,
      )
      triggerBrowserDownload(blob, filename)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 404) toast.error('File not found.')
        else if (err.status === 503) toast.error('Storage unavailable. Try again later.')
        else toast.error(err.displayMessage())
      } else {
        toast.error('Download failed.')
      }
    } finally {
      setDownloading(false)
    }
  }

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border p-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 gap-3">
        <FileIcon className="size-5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 space-y-2">
          <p className="truncate font-medium">{file.original_name}</p>
          <p className="text-xs text-muted-foreground">
            {(file.size_bytes / 1024).toFixed(1)} KB · SHA-256{' '}
            <code className="rounded bg-muted px-1">{shortSha256(file.sha256)}</code>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="ml-1 size-6"
              aria-label="Copy SHA-256"
              onClick={() => {
                void navigator.clipboard.writeText(file.sha256)
                toast.success('SHA-256 copied')
              }}
            >
              <CopyIcon className="size-3" />
            </Button>
          </p>
          <ExtractionBadge
            status={file.extraction_status}
            extractedCharCount={file.extracted_char_count}
            showEmptyHint
          />
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={downloading}
          onClick={() => void onDownload()}
        >
          {downloading ? (
            <Loader2Icon className="size-4 animate-spin" />
          ) : (
            <DownloadIcon className="size-4" />
          )}
          Download
        </Button>
        <Button type="button" variant="secondary" size="sm" onClick={() => setTextOpen(true)}>
          View extracted text
        </Button>
      </div>
      <FormSheet
        open={textOpen}
        onOpenChange={setTextOpen}
        title="Extracted text"
        description="This is exactly what the AI will receive from this file."
        footer={
          <Button type="button" variant="outline" onClick={() => setTextOpen(false)}>
            Close
          </Button>
        }
      >
        {textQuery.isLoading ? <Skeleton className="h-32 w-full" /> : null}
        {textQuery.isError ? (
          <p className="text-sm text-destructive">Could not load extracted text.</p>
        ) : null}
        {textQuery.data ? (
          <PlainTextBlock text={textQuery.data.text || '(empty)'} collapsedLines={20} />
        ) : null}
      </FormSheet>
    </li>
  )
}

function IntakeCard({ input, projectId }: { input: InputRecord; projectId: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {input.is_followup ? 'Follow-up' : 'Initial intake'} · {kindLabel(input.kind)}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <dl className="grid gap-2 sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Received at (client)</dt>
            <dd>{formatAbsoluteDateTime(input.received_at)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Recorded at (system)</dt>
            <dd>{formatAbsoluteDateTime(input.created_at)}</dd>
          </div>
          {input.received_from ? (
            <div className="sm:col-span-2">
              <dt className="text-muted-foreground">Received from</dt>
              <dd>
                <PlainTextBlock text={input.received_from} collapsedLines={3} />
              </dd>
            </div>
          ) : null}
          {input.subject ? (
            <div className="sm:col-span-2">
              <dt className="text-muted-foreground">Subject</dt>
              <dd>
                <PlainTextBlock text={input.subject} collapsedLines={3} />
              </dd>
            </div>
          ) : null}
        </dl>
        <div>
          <p className="mb-2 text-muted-foreground">Body</p>
          <PlainTextBlock text={input.body || '(empty)'} />
        </div>
        {input.files.length > 0 ? (
          <ul className="space-y-3">
            {input.files.map((f) => (
              <AttachmentRow key={f.id} projectId={projectId} file={f} />
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  )
}

function FollowUpSheet({
  open,
  onOpenChange,
  overview,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  overview: ProjectOverview
}) {
  const queryClient = useQueryClient()
  const limitsQuery = useQuery({
    queryKey: ['projects', 'limits'],
    queryFn: getProjectIntakeLimits,
  })
  const [intake, setIntake] = useState<IntakeFieldsState>(() => ({
    kind: 'email',
    receivedAtLocal: localDateTimeInputValue(),
    receivedFrom: '',
    subject: '',
    body: '',
    files: [],
  }))
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      const limits = limitsQuery.data
      if (!limits) throw new Error('Limits not loaded')
      if (!intake.body.trim() && intake.files.length === 0) {
        throw new Error('Provide a body or at least one attachment.')
      }
      if (isReceivedAtInFuture(intake.receivedAtLocal)) {
        throw new Error('Received at cannot be in the future.')
      }
      const { valid } = validateSelectedFiles(intake.files, limits)
      const form = buildFollowUpFormData({
        name: overview.project.name,
        client_name: overview.project.client_name,
        kind: intake.kind,
        received_at: localDateTimeInputToIso(intake.receivedAtLocal),
        received_from: intake.receivedFrom,
        subject: intake.subject,
        body: intake.body,
        files: valid,
      })
      return createFollowUpInput(overview.project.id, form)
    },
    onSuccess: () => {
      toast.success('Follow-up added')
      void queryClient.invalidateQueries({ queryKey: ['projects', overview.project.id] })
      onOpenChange(false)
    },
    onError: (err: Error) => {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setError('Cannot add inputs to an archived or completed project.')
          return
        }
        if (err.status === 503) {
          setError('Storage is temporarily unavailable. Try again later.')
          return
        }
        setError(err.displayMessage())
        return
      }
      setError(err.message)
    },
  })

  return (
    <FormSheet
      open={open}
      onOpenChange={onOpenChange}
      title="Add follow-up"
      description="Follow-up messages are stored and shown on the timeline. They are not used in generated documents yet."
      footer={
        <>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={mutation.isPending || !limitsQuery.data}
            onClick={() => {
              setError(null)
              mutation.mutate()
            }}
          >
            {mutation.isPending ? 'Uploading and extracting text…' : 'Add follow-up'}
          </Button>
        </>
      }
    >
      {limitsQuery.data ? (
        <IntakeFields limits={limitsQuery.data} value={intake} onChange={setIntake} />
      ) : (
        <Skeleton className="h-40 w-full" />
      )}
      {error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}
    </FormSheet>
  )
}

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const location = useLocation()
  const { hasPermission } = useAuth()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<TabId>('overview')
  const [workflowStepKey, setWorkflowStepKey] = useState<string | null>(null)
  const [liveStatusMessage, setLiveStatusMessage] = useState('')
  const [followOpen, setFollowOpen] = useState(false)
  const [confirmArchive, setConfirmArchive] = useState(false)
  const [confirmSettings, setConfirmSettings] = useState(false)
  const [settingsDraft, setSettingsDraft] = useState<'inherit' | 'allow' | 'deny'>('inherit')

  const overviewQuery = useQuery({
    queryKey: ['projects', projectId],
    queryFn: () => getProjectOverview(projectId!),
    enabled: Boolean(projectId),
  })

  const stepsQuery = useProjectStepsQuery(projectId, {
    enabled: Boolean(projectId),
    onStatusAnnounce: setLiveStatusMessage,
  })

  const overview = overviewQuery.data
  useDocumentTitle(overview?.project.name ?? 'Project')

  useEffect(() => {
    if (location.state && typeof location.state === 'object' && 'emptyExtractionWarning' in location.state) {
      toast.warning(
        'Some files had no extractable text. Scanned documents are not supported.',
      )
      window.history.replaceState({}, document.title)
    }
  }, [location.state])

  useEffect(() => {
    if (!overview) return
    const v = overview.project.allow_self_approval
    if (v === null) setSettingsDraft('inherit')
    else if (v) setSettingsDraft('allow')
    else setSettingsDraft('deny')
  }, [overview])

  const initialInput = useMemo(
    () => overview?.inputs.find((i) => !i.is_followup),
    [overview],
  )
  const followUps = useMemo(
    () => overview?.inputs.filter((i) => i.is_followup) ?? [],
    [overview],
  )

  const archiveMutation = useMutation({
    mutationFn: () => archiveProject(projectId!),
    onSuccess: () => {
      toast.success('Project archived')
      void queryClient.invalidateQueries({ queryKey: ['projects', projectId] })
    },
    onError: (err: Error) => {
      toast.error(err instanceof ApiError ? err.displayMessage() : 'Archive failed')
    },
  })

  const restoreMutation = useMutation({
    mutationFn: () => restoreProject(projectId!),
    onSuccess: () => {
      toast.success('Project restored')
      void queryClient.invalidateQueries({ queryKey: ['projects', projectId] })
    },
    onError: (err: Error) => {
      toast.error(err instanceof ApiError ? err.displayMessage() : 'Restore failed')
    },
  })

  const settingsMutation = useMutation({
    mutationFn: (value: boolean | null) => patchProjectSettings(projectId!, value),
    onSuccess: () => {
      toast.success('Project settings updated')
      void queryClient.invalidateQueries({ queryKey: ['projects', projectId] })
    },
    onError: (err: Error) => {
      toast.error(err instanceof ApiError ? err.displayMessage() : 'Update failed')
    },
  })

  if (!projectId) {
    return <EmptyState title="Invalid project" description="Missing project id." />
  }

  if (overviewQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (overviewQuery.isError || !overview) {
    return (
      <EmptyState
        title="Could not load project"
        description="The project may not exist or you may not have access."
        action={
          <Button variant="outline" asChild>
            <Link to="/projects">Back to projects</Link>
          </Button>
        }
      />
    )
  }

  const locked =
    overview.project.status === 'archived' || overview.project.status === 'completed'
  const canFollowUp = hasPermission(PERMISSION_INPUT_ADD) && !locked
  const canArchive = hasPermission(PERMISSION_PROJECT_ARCHIVE)
  const canEditSettings = hasPermission(PERMISSION_SETTINGS_MANAGE)

  const applySettings = () => {
    const next =
      settingsDraft === 'inherit' ? null : settingsDraft === 'allow' ? true : false
    if (next === overview.project.allow_self_approval) return
    settingsMutation.mutate(next)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={overview.project.name}
        description={overview.project.client_name}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <ProjectStatusBadge status={overview.project.status} />
            {canArchive && overview.project.status !== 'archived' ? (
              <Button variant="outline" size="sm" onClick={() => setConfirmArchive(true)}>
                <ArchiveIcon className="size-4" />
                Archive
              </Button>
            ) : null}
            {canArchive && overview.project.status === 'archived' ? (
              <Button variant="outline" size="sm" onClick={() => restoreMutation.mutate()}>
                <RotateCcwIcon className="size-4" />
                Restore
              </Button>
            ) : null}
          </div>
        }
      />

      <div className="flex flex-wrap gap-2 border-b border-border pb-2">
        {(['overview', 'workflow', 'timeline', 'settings'] as TabId[]).map((id) => (
          <Button
            key={id}
            type="button"
            variant={tab === id ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setTab(id)}
          >
            {id.charAt(0).toUpperCase() + id.slice(1)}
          </Button>
        ))}
      </div>

      {tab === 'overview' ? (
        <div className="space-y-6">
          {initialInput ? <IntakeCard input={initialInput} projectId={projectId} /> : null}

          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold">Follow-ups</h2>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button
                      size="sm"
                      disabled={!canFollowUp}
                      onClick={() => setFollowOpen(true)}
                    >
                      Add follow-up
                    </Button>
                  </span>
                </TooltipTrigger>
                {!canFollowUp ? (
                  <TooltipContent>
                    {locked
                      ? 'Cannot add inputs to an archived or completed project.'
                      : 'You do not have permission to add inputs.'}
                  </TooltipContent>
                ) : null}
              </Tooltip>
            </div>
            <p className="text-xs text-muted-foreground">
              Follow-up messages are stored but are not used in generated documents yet.
            </p>
            {followUps.length === 0 ? (
              <p className="text-sm text-muted-foreground">No follow-ups yet.</p>
            ) : (
              followUps.map((inp) => (
                <IntakeCard key={inp.id} input={inp} projectId={projectId} />
              ))
            )}
          </section>

          <Card>
            <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-base">Workflow</CardTitle>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  setWorkflowStepKey(null)
                  setTab('workflow')
                }}
              >
                Open workflow
              </Button>
            </CardHeader>
            <CardContent>
              {stepsQuery.isLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : stepsQuery.data?.steps ? (
                <WorkflowCompactStepper steps={stepsQuery.data.steps} />
              ) : (
                <p className="text-sm text-muted-foreground">Could not load workflow status.</p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {tab === 'workflow' ? (
        <WorkflowTab
          projectId={projectId}
          steps={stepsQuery.data?.steps}
          stepsLoading={stepsQuery.isLoading}
          initialInput={initialInput}
          hasPermission={hasPermission}
          initialStepKey={workflowStepKey}
          liveMessage={liveStatusMessage}
        />
      ) : null}

      {tab === 'timeline' ? (
        <ol className="relative space-y-6 border-l border-border pl-6">
          {overview.timeline.map((entry) => (
            <li key={`${entry.action}-${entry.occurred_at}`} className="relative">
              <span className="absolute -left-[1.35rem] top-1 size-2.5 rounded-full bg-primary" />
              <p className="font-medium">{timelineActionLabel(entry.action)}</p>
              <p className="text-sm text-muted-foreground">{entry.actor_name}</p>
              <Tooltip>
                <TooltipTrigger asChild>
                  <time className="text-xs text-muted-foreground" dateTime={entry.occurred_at}>
                    {formatRelativeTime(entry.occurred_at)}
                  </time>
                </TooltipTrigger>
                <TooltipContent>{formatAbsoluteDateTime(entry.occurred_at)}</TooltipContent>
              </Tooltip>
            </li>
          ))}
        </ol>
      ) : null}

      {tab === 'settings' ? (
        <Card className="max-w-lg">
          <CardHeader>
            <CardTitle className="text-base">Self-approval</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Effective for this project:{' '}
              <strong>
                {overview.effective_allow_self_approval ? 'Allowed' : 'Not allowed'}
              </strong>
            </p>
            <div className="space-y-2">
              <Label htmlFor="self-approval">Override</Label>
              <Select
                value={settingsDraft}
                onValueChange={(v) => setSettingsDraft(v as typeof settingsDraft)}
                disabled={!canEditSettings}
              >
                <SelectTrigger id="self-approval">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="inherit">Use global setting</SelectItem>
                  <SelectItem value="allow">Allow self-approval</SelectItem>
                  <SelectItem value="deny">Do not allow self-approval</SelectItem>
                </SelectContent>
              </Select>
              {!canEditSettings ? (
                <p className="text-xs text-muted-foreground">
                  You can view this setting but cannot change it.
                </p>
              ) : null}
            </div>
            {canEditSettings ? (
              <Button
                type="button"
                disabled={settingsMutation.isPending}
                onClick={() => {
                  const next =
                    settingsDraft === 'inherit'
                      ? null
                      : settingsDraft === 'allow'
                        ? true
                        : false
                  if (next === overview.project.allow_self_approval) {
                    toast.message('No change')
                    return
                  }
                  setConfirmSettings(true)
                }}
              >
                Save
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <FollowUpSheet open={followOpen} onOpenChange={setFollowOpen} overview={overview} />

      <ConfirmDialog
        open={confirmArchive}
        title="Archive this project?"
        description="Archived projects cannot receive new inputs until restored."
        confirmLabel="Archive"
        loading={archiveMutation.isPending}
        onConfirm={() => {
          archiveMutation.mutate()
          setConfirmArchive(false)
        }}
        onCancel={() => setConfirmArchive(false)}
      />
      <ConfirmDialog
        open={confirmSettings}
        title="Update project settings?"
        description="This change is recorded in the audit log."
        confirmLabel="Save"
        destructive={false}
        loading={settingsMutation.isPending}
        onConfirm={() => {
          applySettings()
          setConfirmSettings(false)
        }}
        onCancel={() => setConfirmSettings(false)}
      />
    </div>
  )
}
