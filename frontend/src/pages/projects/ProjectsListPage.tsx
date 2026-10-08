import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2Icon, PlusIcon, SearchIcon } from 'lucide-react'

import { listProjects, type ProjectStatus } from '@/api/projects'
import { EmptyState } from '@/components/layout/EmptyState'
import { PageHeader } from '@/components/layout/PageHeader'
import { ProjectStatusBadge } from '@/components/projects/ProjectStatusBadge'
import { useAuth } from '@/auth/AuthContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { formatAbsoluteDateTime } from '@/lib/formatRelativeTime'
import { PERMISSION_PROJECT_CREATE } from '@/lib/permissions'

const PAGE_SIZE = 20

type StatusFilter = 'all' | ProjectStatus

export function ProjectsListPage() {
  useDocumentTitle('Projects')
  const navigate = useNavigate()
  const { hasPermission } = useAuth()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [page, setPage] = useState(0)

  useEffect(() => {
    const t = window.setTimeout(() => {
      setDebouncedSearch(search)
      setPage(0)
    }, 300)
    return () => window.clearTimeout(t)
  }, [search])

  const query = useQuery({
    queryKey: ['projects', 'list', debouncedSearch, statusFilter, page],
    queryFn: () =>
      listProjects({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        search: debouncedSearch || undefined,
        status: statusFilter === 'all' ? undefined : statusFilter,
      }),
  })

  const total = query.data?.total ?? 0
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1
  const to = Math.min(total, (page + 1) * PAGE_SIZE)
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="space-y-6">
      <PageHeader
        title="Projects"
        description="Client engagements and intake history."
        action={
          hasPermission(PERMISSION_PROJECT_CREATE) ? (
            <Button asChild>
              <Link to="/projects/new">
                <PlusIcon className="size-4" aria-hidden />
                New project
              </Link>
            </Button>
          ) : null
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <SearchIcon className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search by project or client name"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search projects"
          />
        </div>
        <Select
          value={statusFilter}
          onValueChange={(v) => {
            setStatusFilter(v as StatusFilter)
            setPage(0)
          }}
        >
          <SelectTrigger className="w-full sm:w-[180px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="archived">Archived</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {query.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : null}

      {query.isError ? (
        <EmptyState
          title="Could not load projects"
          description="Check your connection and try again."
          action={
            <Button variant="outline" onClick={() => query.refetch()}>
              Retry
            </Button>
          }
        />
      ) : null}

      {query.isSuccess && query.data.items.length === 0 ? (
        <EmptyState
          title="No projects yet"
          description={
            hasPermission(PERMISSION_PROJECT_CREATE)
              ? 'Create a project to log the initial client communication.'
              : 'Projects you can access will appear here.'
          }
          action={
            hasPermission(PERMISSION_PROJECT_CREATE) ? (
              <Button asChild>
                <Link to="/projects/new">New project</Link>
              </Button>
            ) : undefined
          }
        />
      ) : null}

      {query.isSuccess && query.data.items.length > 0 ? (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Project</TableHead>
                  <TableHead>Client</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created by</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data.items.map((row) => (
                  <TableRow
                    key={row.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/projects/${row.id}`)}
                  >
                    <TableCell className="font-medium">{row.name}</TableCell>
                    <TableCell>{row.client_name}</TableCell>
                    <TableCell>
                      <ProjectStatusBadge status={row.status} />
                    </TableCell>
                    <TableCell>{row.created_by_name ?? '—'}</TableCell>
                    <TableCell>{formatAbsoluteDateTime(row.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">
              Showing {from} to {to} of {total}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page + 1 >= pageCount}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      ) : null}

      {query.isFetching && !query.isLoading ? (
        <Loader2Icon className="size-4 animate-spin text-muted-foreground" aria-label="Refreshing" />
      ) : null}
    </div>
  )
}
