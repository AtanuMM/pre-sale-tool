import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

const MAX_COMMENT = 2000

type ApproveStepDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (comment: string | null) => void
  submitting: boolean
  placeholderCount?: number
  numericWarningCount?: number
  requiresProjectCompletionAck?: boolean
}

export function ApproveStepDialog({
  open,
  onOpenChange,
  onConfirm,
  submitting,
  placeholderCount = 0,
  numericWarningCount = 0,
  requiresProjectCompletionAck = false,
}: ApproveStepDialogProps) {
  const [comment, setComment] = useState('')
  const [completionAck, setCompletionAck] = useState(false)

  const handleOpenChange = (v: boolean) => {
    if (!v && !submitting) {
      setComment('')
      setCompletionAck(false)
      onOpenChange(false)
    }
  }

  const handleConfirm = () => {
    const stripped = comment.trim()
    onConfirm(stripped.length > 0 ? stripped : null)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent aria-describedby="approve-step-desc">
        <DialogHeader>
          <DialogTitle>Approve this version?</DialogTitle>
          <DialogDescription id="approve-step-desc">
            After approval, this step output is locked for downstream steps. You can add an
            optional comment for the record.
          </DialogDescription>
        </DialogHeader>
        {requiresProjectCompletionAck ? (
          <div className="space-y-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            <p>
              Approving this specification completes the project. All documents become read-only.
            </p>
            <label className="flex cursor-pointer items-start gap-2">
              <Checkbox
                checked={completionAck}
                onCheckedChange={(v) => setCompletionAck(v === true)}
                disabled={submitting}
              />
              <span>I understand the project will be marked completed.</span>
            </label>
          </div>
        ) : null}
        {(placeholderCount > 0 || numericWarningCount > 0) && (
          <p className="text-sm text-muted-foreground">
            This version has {placeholderCount} open placeholder
            {placeholderCount === 1 ? '' : 's'}
            {numericWarningCount > 0
              ? ` and ${numericWarningCount} “Check this figure” warning${numericWarningCount === 1 ? '' : 's'}`
              : ''}
            . You can still approve.
          </p>
        )}
        <div className="space-y-2">
          <Label htmlFor="approve-comment">Comment (optional)</Label>
          <Textarea
            id="approve-comment"
            value={comment}
            onChange={(e) => setComment(e.target.value.slice(0, MAX_COMMENT))}
            rows={4}
            disabled={submitting}
          />
          <p className="text-xs text-muted-foreground">{comment.length} / {MAX_COMMENT}</p>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={submitting || (requiresProjectCompletionAck && !completionAck)}
          >
            {submitting ? 'Approving…' : 'Approve'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
