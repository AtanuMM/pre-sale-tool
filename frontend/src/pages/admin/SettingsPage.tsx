import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/api/errors'
import { getSettings, updateSettings } from '@/api/settings'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'

export function SettingsPage() {
  const queryClient = useQueryClient()
  const { data, isPending, isError } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const [draft, setDraft] = useState<boolean | null>(null)
  const value = draft ?? data?.allow_self_approval ?? false
  const dirty = data !== undefined && value !== data.allow_self_approval

  const saveMutation = useMutation({
    mutationFn: () => updateSettings({ allow_self_approval: value }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['settings'], updated)
      setDraft(null)
      toast.success('Settings saved.')
    },
    onError: (err: unknown) => {
      toast.error(err instanceof ApiError ? err.displayMessage() : 'Failed to save settings.')
    },
  })

  const helper = useMemo(
    () =>
      'When enabled, users may approve their own step versions unless a project override disables it.',
    [],
  )

  if (isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-40 w-full max-w-xl" />
      </div>
    )
  }

  if (isError || !data) {
    return <p className="text-sm text-destructive">Failed to load settings.</p>
  }

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Global workflow and approval defaults."
      />
      <Card className="max-w-xl shadow-card">
        <CardHeader>
          <CardTitle className="text-base">Approval policy</CardTitle>
          <CardDescription>Controls self-approval behaviour across projects.</CardDescription>
        </CardHeader>
        <CardContent className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <Label htmlFor="self-approval" className="text-sm font-medium">
              Allow self-approval
            </Label>
            <p className="text-sm text-muted-foreground">{helper}</p>
          </div>
          <Switch
            id="self-approval"
            checked={value}
            onCheckedChange={(checked) => setDraft(checked)}
          />
        </CardContent>
      </Card>
      <div className="mt-4 flex items-center gap-3">
        <Button type="button" disabled={!dirty || saveMutation.isPending} onClick={() => saveMutation.mutate()}>
          {saveMutation.isPending ? 'Saving…' : 'Save changes'}
        </Button>
        {dirty && (
          <span className="text-xs text-muted-foreground">You have unsaved changes</span>
        )}
      </div>
    </div>
  )
}
