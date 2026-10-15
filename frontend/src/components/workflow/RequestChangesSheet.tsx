import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { StepInputFields } from '@/components/workflow/StepInputFields'
import type { StepInputField, StepInputValue } from '@/lib/stepLayoutTypes'

export const REQUEST_CHANGES_MAX_LEN = 4000

type RequestChangesSheetProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  text: string
  onTextChange: (value: string) => void
  error: string | null
  onSubmit: () => void
  submitting: boolean
  inputFields?: StepInputField[]
  inputValues?: Record<string, StepInputValue>
  onInputChange?: (key: string, value: StepInputValue) => void
}

export function validateRequestChangesText(
  text: string,
  options?: { allowEmpty?: boolean },
): string | null {
  const stripped = text.trim()
  if (!stripped) {
    if (options?.allowEmpty) return null
    return 'Instructions cannot be empty or whitespace only.'
  }
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
  inputFields = [],
  inputValues = {},
  onInputChange,
}: RequestChangesSheetProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!submitting) onOpenChange(v)
      }}
    >
      <DialogContent
        aria-describedby="request-changes-desc"
        className="flex h-[calc(100vh-2rem)] max-h-[calc(100vh-2rem)] w-[calc(100%-2rem)] max-w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-[calc(100%-2rem)]"
      >
        <DialogHeader className="shrink-0 space-y-1 border-b border-border px-6 py-5 text-left">
          <DialogTitle>Request changes</DialogTitle>
          <DialogDescription id="request-changes-desc">
            Describe what should change in the next revision.
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 min-w-0 flex-1 overflow-auto px-6 py-5">
          {inputFields.length > 0 && onInputChange ? (
            <StepInputFields
              fields={inputFields}
              values={inputValues}
              onChange={onInputChange}
              disabled={submitting}
            />
          ) : null}
          <div className={inputFields.length > 0 && onInputChange ? 'mt-6 space-y-2' : 'space-y-2'}>
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
        </div>
        <DialogFooter className="shrink-0 border-t border-border px-6 py-4 sm:justify-end">
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
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
