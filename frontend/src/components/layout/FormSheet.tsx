import type { ReactNode } from 'react'

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'

type FormSheetProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: ReactNode
  footer: ReactNode
  /** Hide footer (e.g. read-only admin role). */
  hideFooter?: boolean
}

export function FormSheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  hideFooter = false,
}: FormSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        form
        className="flex w-full max-w-[480px] flex-col gap-0 p-0 sm:max-w-[480px]"
      >
        <SheetHeader className="shrink-0 border-b border-border px-6 py-5">
          <SheetTitle>{title}</SheetTitle>
          {description ? <SheetDescription>{description}</SheetDescription> : null}
        </SheetHeader>
        <div
          data-testid="form-sheet-body"
          className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden px-6 py-5"
        >
          {children}
        </div>
        {!hideFooter && (
          <SheetFooter className="shrink-0 flex-row justify-end gap-2 border-t border-border px-6 py-4 sm:flex-row">
            {footer}
          </SheetFooter>
        )}
      </SheetContent>
    </Sheet>
  )
}
