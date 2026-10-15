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
}

export function ApproveStepDialog({
  open,
  onOpenChange,
  onConfirm,
  submitting,
  placeholderCount = 0,
  numericWarningCount = 0,
}: ApproveStepDialogProps) {
  const [comment, setComment] = useState('')

  const handleOpenChange = (v: boolean) => {
    if (!v && !submitting) {
      setComment('')
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
          <Button type="button" onClick={handleConfirm} disabled={submitting}>
            {submitting ? 'Approving…' : 'Approve'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
