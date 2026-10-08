import { useEffect, useState } from 'react'

import { ApiError } from '@/api/errors'
import { getStepVersionPrompt } from '@/api/steps'
import { FormSheet } from '@/components/layout/FormSheet'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PlainTextBlock } from '@/components/projects/PlainTextBlock'

type PromptViewerSheetProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  versionId: string | null
}

export function PromptViewerSheet({
  open,
  onOpenChange,
  versionId,
}: PromptViewerSheetProps) {
  const [prompt, setPrompt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !versionId) {
      setPrompt(null)
      setError(null)
      setLoading(false)
      return
    }
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    setPrompt(null)
    void getStepVersionPrompt(versionId)
      .then((res) => {
        if (controller.signal.aborted) return
        setPrompt(res.assembled_prompt)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        if (err instanceof ApiError) {
          setError(err.displayMessage())
        } else {
          setError('Could not load prompt.')
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [open, versionId])

  return (
    <FormSheet
      open={open}
      onOpenChange={onOpenChange}
      title="Assembled prompt"
      description="Contains client material. Viewing is logged."
      hideFooter
      footer={<span className="sr-only">Actions</span>}
    >
      {loading ? <Skeleton className="h-48 w-full" /> : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {prompt ? (
        <PlainTextBlock text={prompt} collapsedLines={24} className="max-h-[70vh] overflow-y-auto" />
      ) : null}
      <div className="mt-4">
        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
          Close
        </Button>
      </div>
    </FormSheet>
  )
}
