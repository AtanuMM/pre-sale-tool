import { FormSheet } from '@/components/layout/FormSheet'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

export const REQUEST_CHANGES_MAX_LEN = 4000

type RequestChangesSheetProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  text: string
  onTextChange: (value: string) => void
  error: string | null
  onSubmit: () => void
  submitting: boolean
}

export function validateRequestChangesText(text: string): string | null {
  const stripped = text.trim()
  if (!stripped) return 'Instructions cannot be empty or whitespace only.'
  if (stripped.length > REQUEST_CHANGES_MAX_LEN) {
    return `Instructions must be at most ${REQUEST_CHANGES_MAX_LEN} characters.`
  }
  return null
}

export function RequestChangesSheet({
  open,
  onOpenChange,
  text,
  onTextChange,
  error,
  onSubmit,
  submitting,
}: RequestChangesSheetProps) {
  return (
    <FormSheet
      open={open}
      onOpenChange={(v) => {
        if (!submitting) onOpenChange(v)
      }}
      title="Request changes"
      description="Describe what should change in the next revision."
      footer={
        <>
          <Button
            type="button"
            variant="outline"
            disabled={submitting}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button type="button" disabled={submitting} onClick={onSubmit}>
            {submitting ? 'Submitting…' : 'Submit revision request'}
          </Button>
        </>
      }
    >
      <div className="space-y-2">
        <Label htmlFor="revision-instructions">Instructions</Label>
        <Textarea
          id="revision-instructions"
          value={text}
          onChange={(e) => onTextChange(e.target.value)}
          rows={8}
          disabled={submitting}
          aria-invalid={error ? true : undefined}
        />
        <p className="text-xs text-muted-foreground">
          {text.length} / {REQUEST_CHANGES_MAX_LEN} characters (whitespace trimmed on send)
        </p>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
      </div>
    </FormSheet>
  )
}
