import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDownIcon, Loader2Icon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/api/errors'
import { triggerBrowserDownload } from '@/api/download'
import type { InputRecord } from '@/api/projects'
import {
  approveStepVersion,
  downloadStepVersion,
  generateStep,
  getStepVersionDetail,
  getStepVersions,
  requestStepChanges,
  type ProjectStep,
  type StepVersionSummary,
} from '@/api/steps'
import { generationFailureHint } from '@/lib/generationFailureHints'
import { ExtractionBadge } from '@/components/projects/ExtractionBadge'
import { ApproveStepDialog } from '@/components/workflow/ApproveStepDialog'
import { GenerationElapsed } from '@/components/workflow/GenerationElapsed'
import { PromptViewerSheet } from '@/components/workflow/PromptViewerSheet'
import { RequestChangesSheet, validateRequestChangesText } from '@/components/workflow/RequestChangesSheet'
import { GenericStepViewer } from '@/components/workflow/GenericStepViewer'
import { StepInputFields } from '@/components/workflow/StepInputFields'
import { VersionHistoryPanel } from '@/components/workflow/VersionHistoryPanel'
import { generationStartIso } from '@/components/workflow/workflowSelection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { formatAbsoluteDateTime } from '@/lib/formatRelativeTime'
import {
  PERMISSION_DOCUMENT_DOWNLOAD,
  PERMISSION_PROMPT_VIEW,
  PERMISSION_STEP_APPROVE,
  PERMISSION_STEP_GENERATE,
  PERMISSION_STEP_REQUEST_CHANGES,
} from '@/lib/permissions'
import {
  exportFormatLabel,
  stepVersionCanDownload,
  stepVersionDownloadLabel,
  stepVersionDownloadToastError,
} from '@/lib/stepVersionDownload'
import { collectStepInputs, defaultInputValues, parseUserInputs } from '@/lib/stepInputValues'
import type { StepInputValue } from '@/lib/stepLayoutTypes'
import { syncWorkflowAfter409, syncWorkflowAfterMutation } from '@/lib/workflowQuerySync'

type StepPanelProps = {
  projectId: string
  step: ProjectStep
  initialInput: InputRecord | undefined
  hasPermission: (code: string) => boolean
}

export function StepPanel({
  projectId,
  step,
  initialInput,
  hasPermission,
}: StepPanelProps) {
  const queryClient = useQueryClient()
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [requestOpen, setRequestOpen] = useState(false)
  const [requestText, setRequestText] = useState('')
  const [requestError, setRequestError] = useState<string | null>(null)
  const [approveOpen, setApproveOpen] = useState(false)
  const [promptOpen, setPromptOpen] = useState(false)
  const [downloadingVersionId, setDownloadingVersionId] = useState<string | null>(
    null,
  )
  const [draftInputs, setDraftInputs] = useState<Record<string, StepInputValue>>({})
  const [requestInputs, setRequestInputs] = useState<Record<string, StepInputValue>>({})

  const currentVersionId = step.current_version_id
  const displayVersionId =
    selectedVersionId ?? currentVersionId ?? step.latest_version?.id ?? null

  useEffect(() => {
    setSelectedVersionId(null)
  }, [step.key, step.current_version_id])

  useEffect(() => {
    setDraftInputs(defaultInputValues(step.input_fields))
    // Defaults follow the step identity; field specs are stable per step key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step.key])

  const versionsQuery = useQuery({
    queryKey: ['projects', projectId, 'steps', step.key, 'versions'],
    queryFn: () => getStepVersions(projectId, step.key),
    enabled: step.implemented,
  })

  const detailQuery = useQuery({
    queryKey: ['step-versions', displayVersionId],
    queryFn: () => getStepVersionDetail(displayVersionId!),
    enabled: Boolean(displayVersionId),
  })

  const generatingDetailQuery = useQuery({
    queryKey: ['step-versions', step.latest_version?.id, 'generating-elapsed'],
    queryFn: () => getStepVersionDetail(step.latest_version!.id),
    enabled:
      step.status === 'generating' && Boolean(step.latest_version?.id),
    refetchInterval: step.status === 'generating' ? 3000 : false,
  })

  const generationStart = generationStartIso(
    generatingDetailQuery.data ?? detailQuery.data,
    step.latest_version,
  )

  const isReadOnlyHistory =
    displayVersionId != null &&
    currentVersionId != null &&
    displayVersionId !== currentVersionId

  const canShowGenerate = hasPermission(PERMISSION_STEP_GENERATE)
  const canShowRequestChanges = hasPermission(PERMISSION_STEP_REQUEST_CHANGES)
  const canShowApprove = hasPermission(PERMISSION_STEP_APPROVE)
  const canShowPrompt = hasPermission(PERMISSION_PROMPT_VIEW)
  const canShowDownload = hasPermission(PERMISSION_DOCUMENT_DOWNLOAD)

  const detailHasExportableContent =
    detailQuery.data?.content != null &&
    Object.keys(detailQuery.data.content).length > 0 &&
    detailQuery.data.status != null &&
    stepVersionCanDownload(detailQuery.data.status)

  const handleDownloadVersion = async (
    version: StepVersionSummary,
    format = 'docx',
  ) => {
    setDownloadingVersionId(version.id)
    try {
      const fallback = `${step.key}-v${version.version_no}.${format}`
      const { blob, filename } = await downloadStepVersion(version.id, format, fallback)
      triggerBrowserDownload(blob, filename)
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(
          stepVersionDownloadToastError(err.status, err.displayMessage()),
        )
      } else {
        const msg = err instanceof Error ? err.message : ''
        toast.error(msg || 'Download failed.')
      }
    } finally {
      setDownloadingVersionId(null)
    }
  }

  const handleMutationError = async (err: unknown, versionId?: string) => {
    if (err instanceof ApiError) {
      toast.error(err.displayMessage())
      if (err.status === 409) {
        await syncWorkflowAfter409(queryClient, projectId, step.key, versionId)
      }
    } else {
      toast.error('Request failed')
    }
  }

  const generateMutation = useMutation({
    mutationFn: () => {
      const inputs = collectStepInputs(step.input_fields, draftInputs)
      return generateStep(
        projectId,
        step.key,
        Object.keys(inputs).length > 0 ? inputs : undefined,
      )
    },
    onSuccess: async () => {
      toast.success('Generation started')
      setDraftInputs(defaultInputValues(step.input_fields))
      await syncWorkflowAfterMutation(queryClient, projectId, step.key)
    },
    onError: (err) => void handleMutationError(err),
  })

  const requestMutation = useMutation({
    mutationFn: (instructions: string | null) => {
      const inputs =
        step.input_fields.length > 0
          ? collectStepInputs(step.input_fields, requestInputs)
          : undefined
      return requestStepChanges(currentVersionId!, instructions, inputs)
    },
    onSuccess: async () => {
      toast.success('Revision requested')
      setRequestOpen(false)
      setRequestText('')
      setRequestError(null)
      await syncWorkflowAfterMutation(queryClient, projectId, step.key)
    },
    onError: async (err) => {
      await handleMutationError(err, currentVersionId ?? undefined)
    },
  })

  const approveMutation = useMutation({
    mutationFn: (comment: string | null) =>
      approveStepVersion(currentVersionId!, comment),
    onSuccess: async () => {
      toast.success('Step approved')
      setApproveOpen(false)
      await syncWorkflowAfterMutation(queryClient, projectId, step.key, currentVersionId!)
    },
    onError: async (err) => {
      await handleMutationError(err, currentVersionId ?? undefined)
    },
  })

  if (step.status === 'locked') {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Locked</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {step.blocked_reason ?? 'Complete previous steps before working on this one.'}
        </CardContent>
      </Card>
    )
  }

  if (!step.implemented) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Coming soon</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>This step is not available in ScopeDesk yet.</p>
          {step.blocked_reason ? <p>{step.blocked_reason}</p> : null}
        </CardContent>
      </Card>
    )
  }

  if (step.status === 'ready') {
    return (
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Ready to generate</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            {step.reads_description ? (
              <p>{step.reads_description}</p>
            ) : null}
            {step.context_steps.length > 0 ? (
              <div className="space-y-1">
                <p className="font-medium">Uses approved outputs from:</p>
                <ul className="list-disc pl-5">
                  {step.context_steps.map((ctx) => (
                    <li key={ctx.key}>{ctx.title}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {step.writes_description ? (
              <p className="text-muted-foreground">{step.writes_description}</p>
            ) : null}
            {initialInput ? (
              <div className="rounded-lg border border-border p-3 space-y-2">
                <p className="font-medium">{initialInput.subject ?? 'Initial intake'}</p>
                <p className="text-muted-foreground line-clamp-3 whitespace-pre-wrap break-words">
                  {initialInput.body}
                </p>
                {initialInput.files.length > 0 ? (
                  <ul className="space-y-1">
                    {initialInput.files.map((f) => (
                      <li key={f.id} className="flex flex-wrap items-center gap-2 text-xs">
                        <span>{f.original_name}</span>
                        <ExtractionBadge
                          status={f.extraction_status}
                          extractedCharCount={f.extracted_char_count}
                        />
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
            {step.has_failed_attempt && step.latest_version?.error ? (
              <div className="space-y-1">
                <p className="text-destructive">{step.latest_version.error}</p>
                {step.latest_version.generation_progress ? (
                  <p className="text-sm text-muted-foreground">
                    Last run stopped at step {step.latest_version.generation_progress.done} of{' '}
                    {step.latest_version.generation_progress.total}.
                  </p>
                ) : null}
                {step.latest_version.failure_detail ? (
                  <p className="text-sm text-muted-foreground">
                    {step.latest_version.failure_detail}
                  </p>
                ) : null}
                {(() => {
                  const hint = generationFailureHint(step.latest_version.failure_code)
                  return hint ? (
                    <p className="text-sm text-muted-foreground">{hint}</p>
                  ) : null
                })()}
              </div>
            ) : null}
            {step.key === 'sprint_plan' ? (
              <p className="text-muted-foreground">
                Team and capacity are read from the approved estimate. To change the team, revise
                the estimate.
              </p>
            ) : null}
            <StepInputFields
              fields={step.input_fields}
              values={draftInputs}
              onChange={(key, value) =>
                setDraftInputs((prev) => ({ ...prev, [key]: value }))
              }
              disabled={generateMutation.isPending}
            />
            {canShowGenerate ? (
              <div className="space-y-2">
                <Button
                  type="button"
                  disabled={!step.can_generate || generateMutation.isPending}
                  onClick={() => generateMutation.mutate()}
                >
                  {generateMutation.isPending ? 'Starting…' : 'Generate'}
                </Button>
                {!step.can_generate && step.blocked_reason ? (
                  <p className="text-sm text-muted-foreground">{step.blocked_reason}</p>
                ) : null}
                {step.has_failed_attempt ? (
                  <p className="text-sm text-muted-foreground">Try again when ready.</p>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    )
  }

  if (step.status === 'generating') {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Loader2Icon className="size-5 animate-spin" aria-hidden />
            Generating
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {(() => {
            const progress =
              generatingDetailQuery.data?.inputs?.generation_progress ??
              step.generation_progress
            const done =
              progress && typeof progress === 'object' && typeof (progress as { done?: unknown }).done === 'number'
                ? (progress as { done: number }).done
                : null
            const total =
              progress && typeof progress === 'object' && typeof (progress as { total?: unknown }).total === 'number'
                ? (progress as { total: number }).total
                : null
            if (step.key === 'estimate' && done != null && total != null && total > 0) {
              return <p>Estimating batch {done} of {total}.</p>
            }
            if (step.key === 'srs' && done != null && total != null && total > 0) {
              return <p>Writing the SRS, part {done} of {total}.</p>
            }
            if (step.key === 'sprint_plan' && done != null && total != null && total > 0) {
              return <p>Planning the sprints, part {done} of {total}.</p>
            }
            return <p>Reading inputs and writing the output. This usually takes under a minute.</p>
          })()}
          <p className="text-muted-foreground">
            Elapsed: <GenerationElapsed startIso={generationStart} />
          </p>
        </CardContent>
      </Card>
    )
  }

  const showFailedRevisionNotice =
    step.status === 'in_review' && step.has_failed_attempt

  const showActionBar =
    step.status === 'in_review' &&
    !isReadOnlyHistory &&
    (canShowRequestChanges || canShowApprove)

  return (
    <div className="space-y-4">
      {step.status === 'in_review' ? (
        <div
          className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm"
          role="status"
        >
          Draft, not approved
        </div>
      ) : null}
      {step.status === 'approved' ? (
        <div
          className="rounded-lg border border-success-subtle bg-success-subtle/30 px-4 py-3 text-sm space-y-1"
          role="status"
        >
          <p className="font-medium">Approved</p>
          {detailQuery.data?.approval ? (
            <>
              <p className="text-muted-foreground">
                {detailQuery.data.approval.approved_by_name ?? 'Unknown'} ·{' '}
                {formatAbsoluteDateTime(detailQuery.data.approval.approved_at)}
              </p>
              {detailQuery.data.approval.comment ? (
                <p className="whitespace-pre-wrap break-words">
                  {detailQuery.data.approval.comment}
                </p>
              ) : null}
              {detailQuery.data.approval.self_approved ? (
                <Badge variant="outline">Self-approved</Badge>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
      {step.status === 'stale' ? (
        <div className="rounded-lg border border-border bg-muted/50 px-4 py-3 text-sm" role="status">
          This output is stale. Regeneration and reopen flows are not available yet in the
          UI.
        </div>
      ) : null}
      {showFailedRevisionNotice ? (
        <p className="text-sm text-muted-foreground" role="status">
          The last revision failed; your reviewed version is unchanged.
        </p>
      ) : null}
      {isReadOnlyHistory ? (
        <p className="text-sm font-medium text-muted-foreground">
          Viewing an older version (read-only)
        </p>
      ) : null}

      <div className="flex flex-col gap-6 lg:flex-row">
        {versionsQuery.data ? (
          <VersionHistoryPanel
            className="lg:w-56 shrink-0"
            versions={versionsQuery.data}
            selectedId={displayVersionId}
            currentVersionId={currentVersionId}
            onSelect={setSelectedVersionId}
            canDownload={canShowDownload}
            downloadingVersionId={downloadingVersionId}
            onDownload={(v) => void handleDownloadVersion(v)}
          />
        ) : (
          <Skeleton className="h-40 w-full lg:w-56" />
        )}
        <div className="min-w-0 flex-1 space-y-4">
          {detailQuery.data?.instructions ? (
            <div className="rounded-lg border border-border p-3 text-xs">
              <p className="font-medium">Revision instructions</p>
              <p className="mt-1 whitespace-pre-wrap break-words text-muted-foreground">
                {detailQuery.data.instructions}
              </p>
            </div>
          ) : null}
          {detailQuery.isLoading ? <Skeleton className="h-64 w-full" /> : null}
          {detailQuery.data?.content &&
          Object.keys(detailQuery.data.content).length > 0 &&
          (detailQuery.data.layout ?? step.layout).length > 0 ? (
            <GenericStepViewer
              layout={detailQuery.data.layout ?? step.layout}
              content={{
                ...detailQuery.data.content,
                version_id: displayVersionId ?? detailQuery.data.id,
              }}
            />
          ) : detailQuery.isSuccess ? (
            <p className="text-sm text-muted-foreground">No output content for this version.</p>
          ) : null}
        </div>
      </div>

      {canShowDownload && displayVersionId && detailHasExportableContent ? (
        <div className="flex flex-wrap items-center gap-3">
          {(step.export_formats ?? ['docx']).length > 1 ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  disabled={downloadingVersionId === displayVersionId}
                >
                  {downloadingVersionId === displayVersionId ? (
                    <>
                      <Loader2Icon className="size-4 animate-spin" aria-hidden />
                      Downloading…
                    </>
                  ) : (
                    <>
                      Download
                      <ChevronDownIcon className="size-4" aria-hidden />
                    </>
                  )}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                {(step.export_formats ?? ['docx']).map((fmt) => (
                  <DropdownMenuItem
                    key={fmt}
                    onSelect={() => {
                      const v = versionsQuery.data?.find((row) => row.id === displayVersionId)
                      if (v) void handleDownloadVersion(v, fmt)
                    }}
                  >
                    {exportFormatLabel(fmt, detailQuery.data!.status)}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Button
              type="button"
              variant="outline"
              disabled={downloadingVersionId === displayVersionId}
              onClick={() => {
                const v = versionsQuery.data?.find((row) => row.id === displayVersionId)
                if (v) void handleDownloadVersion(v)
              }}
            >
              {downloadingVersionId === displayVersionId ? (
                <>
                  <Loader2Icon className="size-4 animate-spin" aria-hidden />
                  Downloading…
                </>
              ) : (
                stepVersionDownloadLabel(detailQuery.data!.status)
              )}
            </Button>
          )}
        </div>
      ) : null}

      {showActionBar ? (
        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
          {canShowRequestChanges ? (
            <Button
              type="button"
              variant="outline"
              disabled={!step.can_request_changes || requestMutation.isPending}
              onClick={() => {
                setRequestInputs(
                  parseUserInputs(detailQuery.data?.inputs?.user_inputs, step.input_fields),
                )
                setRequestOpen(true)
              }}
            >
              Request changes
            </Button>
          ) : null}
          {canShowApprove ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                disabled={!step.can_approve || approveMutation.isPending}
                onClick={() => setApproveOpen(true)}
              >
                Approve
              </Button>
              {!step.can_approve && step.approve_blocked_reason ? (
                <p className="text-sm text-muted-foreground">{step.approve_blocked_reason}</p>
              ) : null}
            </div>
          ) : null}
          {canShowPrompt && displayVersionId ? (
            <Button type="button" variant="ghost" size="sm" onClick={() => setPromptOpen(true)}>
              View prompt
            </Button>
          ) : null}
        </div>
      ) : null}

      {!showActionBar && canShowPrompt && displayVersionId ? (
        <Button type="button" variant="ghost" size="sm" onClick={() => setPromptOpen(true)}>
          View prompt
        </Button>
      ) : null}

      <RequestChangesSheet
        open={requestOpen}
        onOpenChange={setRequestOpen}
        text={requestText}
        onTextChange={setRequestText}
        error={requestError}
        submitting={requestMutation.isPending}
        inputFields={step.input_fields}
        inputValues={requestInputs}
        onInputChange={(key, value) =>
          setRequestInputs((prev) => ({ ...prev, [key]: value }))
        }
        onSubmit={() => {
          const trimmed = requestText.trim()
          const allowEmpty =
            step.supports_reassemble === true &&
            step.input_fields.length > 0 &&
            JSON.stringify(collectStepInputs(step.input_fields, requestInputs)) !==
              JSON.stringify(
                collectStepInputs(
                  step.input_fields,
                  parseUserInputs(
                    detailQuery.data?.inputs?.user_inputs,
                    step.input_fields,
                  ),
                ),
              )
          const err = validateRequestChangesText(requestText, {
            allowEmpty,
          })
          if (err) {
            setRequestError(err)
            return
          }
          setRequestError(null)
          if (!currentVersionId) return
          requestMutation.mutate(trimmed || null)
        }}
      />
      <ApproveStepDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        submitting={approveMutation.isPending}
        placeholderCount={
          typeof (detailQuery.data?.content?.viewer as Record<string, unknown> | undefined)
            ?.placeholder_count === 'number'
            ? ((detailQuery.data!.content!.viewer as Record<string, unknown>)
                .placeholder_count as number)
            : 0
        }
        numericWarningCount={
          Array.isArray(
            (detailQuery.data?.content?.viewer as Record<string, unknown> | undefined)
              ?.numeric_claim_warnings,
          )
            ? (
                (detailQuery.data!.content!.viewer as Record<string, unknown>)
                  .numeric_claim_warnings as unknown[]
              ).length
            : 0
        }
        requiresProjectCompletionAck={step.key === 'frs'}
        onConfirm={(comment) => approveMutation.mutate(comment)}
      />
      <PromptViewerSheet
        open={promptOpen}
        onOpenChange={setPromptOpen}
        versionId={displayVersionId}
      />
    </div>
  )
}
