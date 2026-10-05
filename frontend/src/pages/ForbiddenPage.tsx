import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export function ForbiddenPage() {
  useDocumentTitle('Forbidden')
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center gap-4 py-16 text-center">
      <p className="text-4xl font-semibold text-destructive">403</p>
      <p className="text-muted-foreground">You do not have permission to view this page.</p>
      <Button asChild variant="outline">
        <Link to="/">Back to dashboard</Link>
      </Button>
    </div>
  )
}
