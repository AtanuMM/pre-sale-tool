import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2Icon } from 'lucide-react'
import { toast } from 'sonner'

import { ApiError } from '@/api/errors'
import {
  buildCreateProjectFormData,
  createProject,
  getProjectIntakeLimits,
  type InputKind,
} from '@/api/projects'
import { IntakeFields, type IntakeFieldsState } from '@/components/projects/IntakeFields'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import {
  isReceivedAtInFuture,
  localDateTimeInputToIso,
  localDateTimeInputValue,
  validateSelectedFiles,
} from '@/lib/validateIntakeFiles'

export function NewProjectPage() {
  useDocumentTitle('New project')
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [clientName, setClientName] = useState('')
  const [intake, setIntake] = useState<IntakeFieldsState>(() => ({
    kind: 'email' as InputKind,
    receivedAtLocal: localDateTimeInputValue(),
    receivedFrom: '',
    subject: '',
    body: '',
    files: [],
  }))
  const [formError, setFormError] = useState<string | null>(null)
  const [fileIssues, setFileIssues] = useState<string[]>([])

  const limitsQuery = useQuery({
    queryKey: ['projects', 'limits'],
    queryFn: getProjectIntakeLimits,
    staleTime: 60_000,
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      const limits = limitsQuery.data
      if (!limits) throw new Error('Limits not loaded')
      if (!name.trim() || !clientName.trim()) {
        throw new Error('Project name and client name are required.')
      }
      if (!intake.body.trim() && intake.files.length === 0) {
        throw new Error('Provide a body or at least one attachment.')
      }
      if (isReceivedAtInFuture(intake.receivedAtLocal)) {
        throw new Error('Received at cannot be in the future.')
      }
      const { valid, issues } = validateSelectedFiles(intake.files, limits)
      if (issues.length) {
        setFileIssues(issues.map((i) => `${i.file.name}: ${i.message}`))
        throw new Error('Fix attachment issues before submitting.')
      }
      const form = buildCreateProjectFormData({
        name: name.trim(),
        client_name: clientName.trim(),
        kind: intake.kind,
        received_at: localDateTimeInputToIso(intake.receivedAtLocal),
        received_from: intake.receivedFrom,
        subject: intake.subject,
        body: intake.body,
        files: valid,
      })
      return createProject(form)
    },
    onSuccess: (data) => {
      toast.success('Project created')
      const hasEmpty = data.files.some((f) => f.extraction_status === 'empty')
      navigate(`/projects/${data.project.id}`, {
        state: hasEmpty ? { emptyExtractionWarning: true } : undefined,
      })
    },
    onError: (err: Error) => {
      if (err instanceof ApiError) {
        if (err.status === 503) {
          setFormError('Storage is temporarily unavailable. Wait a moment and try again.')
          return
        }
        if (err.status === 413) {
          setFormError(err.displayMessage())
          return
        }
        setFormError(err.displayMessage())
        return
      }
      setFormError(err.message)
    },
  })

  const submitting = createMutation.isPending

  if (limitsQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  if (limitsQuery.isError || !limitsQuery.data) {
    return (
      <div className="space-y-4">
        <PageHeader title="New project" />
        <p className="text-sm text-destructive">Could not load upload limits. Try again later.</p>
        <Button variant="outline" onClick={() => limitsQuery.refetch()}>
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title="New project"
        description="Log the initial client communication and attachments."
      />

      <form
        className="space-y-6"
        onSubmit={(e) => {
          e.preventDefault()
          setFormError(null)
          setFileIssues([])
          createMutation.mutate()
        }}
      >
        <Card>
          <CardHeader>
            <CardTitle>Project</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="proj-name">Project name</Label>
              <Input
                id="proj-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={submitting}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="proj-client">Client name</Label>
              <Input
                id="proj-client"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                disabled={submitting}
                required
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Initial client communication</CardTitle>
          </CardHeader>
          <CardContent>
            <IntakeFields
              limits={limitsQuery.data}
              value={intake}
              onChange={setIntake}
              disabled={submitting}
              fileIssues={fileIssues}
            />
          </CardContent>
        </Card>

        {formError ? <p className="text-sm text-destructive">{formError}</p> : null}

        <div className="flex flex-wrap gap-3">
          <Button type="submit" disabled={submitting}>
            {submitting ? (
              <>
                <Loader2Icon className="size-4 animate-spin" aria-hidden />
                Uploading and extracting text…
              </>
            ) : (
              'Create project'
            )}
          </Button>
          <Button type="button" variant="outline" asChild disabled={submitting}>
            <Link to="/projects">Cancel</Link>
          </Button>
        </div>
      </form>
    </div>
  )
}
