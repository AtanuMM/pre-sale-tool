import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import {
  Loader2Icon,
  MoreHorizontalIcon,
  PlusIcon,
  SearchIcon,
} from 'lucide-react'
import { toast } from 'sonner'

import { ApiError } from '@/api/errors'
import { listRoles } from '@/api/roles'
import { createUser, listUsers, resetUserPassword, updateUser } from '@/api/users'
import type { UserAdmin } from '@/api/types'
import { ConfirmDialog } from '@/components/layout/ConfirmDialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { EmptyState } from '@/components/layout/EmptyState'
import { PageHeader } from '@/components/layout/PageHeader'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { FormSheet } from '@/components/layout/FormSheet'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { filterUsers, type UserStatusFilter } from '@/lib/filterUsers'
import { formatAbsoluteDateTime, formatRelativeTime } from '@/lib/formatRelativeTime'
import { userInitials } from '@/lib/userInitials'

const MIN_PASSWORD = 12
const PAGE_SIZE = 20

export function UsersPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<UserStatusFilter>('all')
  const [page, setPage] = useState(0)

  const usersQuery = useQuery({
    queryKey: ['users', 'admin-list'],
    queryFn: () => listUsers({ limit: 100, offset: 0 }),
  })
  const rolesQuery = useQuery({ queryKey: ['roles'], queryFn: listRoles })

  const [sheetMode, setSheetMode] = useState<'create' | 'edit' | null>(null)
  const [editUser, setEditUser] = useState<UserAdmin | null>(null)
  const [confirmDeactivate, setConfirmDeactivate] = useState<UserAdmin | null>(null)
  const [confirmReset, setConfirmReset] = useState<UserAdmin | null>(null)
  const [resetPassword, setResetPassword] = useState('')

  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [roleIds, setRoleIds] = useState<Set<string>>(new Set())
  const [editFullName, setEditFullName] = useState('')
  const [editActive, setEditActive] = useState(true)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const roles = rolesQuery.data ?? []

  const filtered = useMemo(
    () => filterUsers(usersQuery.data?.items ?? [], search, statusFilter),
    [usersQuery.data, search, statusFilter],
  )

  const totalFiltered = filtered.length
  const pageCount = Math.max(1, Math.ceil(totalFiltered / PAGE_SIZE))
  const safePage = Math.min(page, pageCount - 1)
  const pageItems = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE)
  const from = totalFiltered === 0 ? 0 : safePage * PAGE_SIZE + 1
  const to = Math.min((safePage + 1) * PAGE_SIZE, totalFiltered)

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['users'] })

  const createMutation = useMutation({
    mutationFn: () =>
      createUser({
        email: email.trim(),
        full_name: fullName.trim(),
        password,
        role_ids: [...roleIds],
      }),
    onSuccess: () => {
      invalidate()
      closeSheet()
      toast.success('User created.')
    },
    onError: (err: unknown) => {
      toast.error(err instanceof ApiError ? err.displayMessage() : 'Could not create user.')
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!editUser) throw new Error('No user')
      return updateUser(editUser.id, {
        full_name: editFullName.trim(),
        is_active: editActive,
        role_ids: [...roleIds],
      })
    },
    onSuccess: () => {
      invalidate()
      closeSheet()
      toast.success('User updated.')
    },
    onError: (err: unknown) => {
      toast.error(err instanceof ApiError ? err.displayMessage() : 'Could not update user.')
    },
  })

  const deactivateMutation = useMutation({
    mutationFn: (user: UserAdmin) => updateUser(user.id, { is_active: false }),
    onSuccess: () => {
      invalidate()
      setConfirmDeactivate(null)
      toast.success('User deactivated.')
    },
    onError: (err: unknown) => {
      toast.error(err instanceof ApiError ? err.displayMessage() : 'Could not deactivate user.')
    },
  })

  const reactivateMutation = useMutation({
    mutationFn: (user: UserAdmin) => updateUser(user.id, { is_active: true }),
    onSuccess: () => {
      invalidate()
      toast.success('User reactivated.')
    },
    onError: (err: unknown) => {
      toast.error(err instanceof ApiError ? err.displayMessage() : 'Could not reactivate user.')
    },
  })

  const resetMutation = useMutation({
    mutationFn: () => {
      if (!confirmReset) throw new Error('No user')
      return resetUserPassword(confirmReset.id, { password: resetPassword })
    },
    onSuccess: () => {
      setConfirmReset(null)
      setResetPassword('')
      toast.success('Password reset.')
    },
    onError: (err: unknown) => {
      toast.error(err instanceof ApiError ? err.displayMessage() : 'Could not reset password.')
    },
  })

  function closeSheet() {
    setSheetMode(null)
    setEditUser(null)
    setFieldErrors({})
  }

  function openCreate() {
    setEmail('')
    setFullName('')
    setPassword('')
    setRoleIds(new Set())
    setFieldErrors({})
    setSheetMode('create')
  }

  function openEdit(user: UserAdmin) {
    setEditUser(user)
    setEditFullName(user.full_name)
    setEditActive(user.is_active)
    setRoleIds(new Set(user.roles.map((r) => r.id)))
    setFieldErrors({})
    setSheetMode('edit')
  }

  function validateCreate(): boolean {
    const errors: Record<string, string> = {}
    if (password.length < MIN_PASSWORD) {
      errors.password = `At least ${MIN_PASSWORD} characters.`
    }
    if (roleIds.size === 0) errors.roles = 'Select at least one role.'
    setFieldErrors(errors)
    return Object.keys(errors).length === 0
  }

  function submitSheet() {
    if (sheetMode === 'create') {
      if (!validateCreate()) return
      createMutation.mutate()
    } else if (sheetMode === 'edit') {
      if (roleIds.size === 0) {
        setFieldErrors({ roles: 'Select at least one role.' })
        return
      }
      updateMutation.mutate()
    }
  }

  return (
    <div>
      <PageHeader
        title="Users"
        description="Manage accounts, roles, and access."
        action={
          <Button type="button" onClick={openCreate}>
            <PlusIcon className="size-4" />
            Create user
          </Button>
        }
      />

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1 sm:max-w-xs">
          <SearchIcon className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search users…"
            className="pl-9"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(0)
            }}
          />
        </div>
        <Select
          value={statusFilter}
          onValueChange={(v) => {
            setStatusFilter(v as UserStatusFilter)
            setPage(0)
          }}
        >
          <SelectTrigger className="w-full sm:w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-card shadow-card">
        <Table>
          <TableHeader className="sticky top-0 z-10 bg-card">
            <TableRow className="hover:bg-transparent">
              <TableHead>User</TableHead>
              <TableHead>Roles</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last login</TableHead>
              <TableHead className="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {usersQuery.isPending &&
              [1, 2, 3, 4, 5].map((i) => (
                <TableRow key={i}>
                  <TableCell colSpan={5}>
                    <Skeleton className="h-10 w-full" />
                  </TableCell>
                </TableRow>
              ))}
            {!usersQuery.isPending && pageItems.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="p-0">
                  <EmptyState
                    title="No users found"
                    description="Try adjusting search or filters, or create a new user."
                  />
                </TableCell>
              </TableRow>
            )}
            {pageItems.map((user) => (
              <TableRow key={user.id} className="group">
                <TableCell>
                  <div className="flex items-center gap-3">
                    <Avatar className="size-9">
                      <AvatarFallback className="bg-muted text-xs">
                        {userInitials(user.full_name, user.email)}
                      </AvatarFallback>
                    </Avatar>
                    <div>
                      <p className="text-sm font-medium">{user.full_name}</p>
                      <p className="text-xs text-muted-foreground">{user.email}</p>
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {user.roles.map((r) => (
                      <Badge key={r.id} variant="outline" className="bg-secondary/80">
                        {r.name}
                      </Badge>
                    ))}
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={user.is_active ? 'success' : 'inactive'}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="cursor-default text-sm text-muted-foreground">
                        {formatRelativeTime(user.last_login_at)}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>{formatAbsoluteDateTime(user.last_login_at)}</TooltipContent>
                  </Tooltip>
                </TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="size-8" aria-label="Row actions">
                        <MoreHorizontalIcon className="size-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => openEdit(user)}>Edit</DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setConfirmReset(user)}>
                        Reset password
                      </DropdownMenuItem>
                      {user.is_active ? (
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onClick={() => setConfirmDeactivate(user)}
                        >
                          Deactivate
                        </DropdownMenuItem>
                      ) : (
                        <DropdownMenuItem onClick={() => reactivateMutation.mutate(user)}>
                          Reactivate
                        </DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {totalFiltered > 0 && (
        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {from} to {to} of {totalFiltered}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={safePage === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={safePage >= pageCount - 1}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <FormSheet
        open={sheetMode !== null}
        onOpenChange={(o) => !o && closeSheet()}
        title={sheetMode === 'create' ? 'Create user' : 'Edit user'}
        description={
          sheetMode === 'create'
            ? 'Add an account and assign roles.'
            : 'Update profile, status, and roles.'
        }
        footer={
          <>
            <Button variant="outline" onClick={closeSheet}>
              Cancel
            </Button>
            <Button
              onClick={submitSheet}
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              {(createMutation.isPending || updateMutation.isPending) && (
                <Loader2Icon className="size-4 animate-spin" />
              )}
              Save
            </Button>
          </>
        }
      >
        <div className="space-y-4">
            {sheetMode === 'create' && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="u-email">Email</Label>
                  <Input id="u-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="u-name">Full name</Label>
                  <Input id="u-name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="u-pass">Initial password</Label>
                  <Input
                    id="u-pass"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    aria-invalid={!!fieldErrors.password}
                  />
                  {fieldErrors.password && (
                    <p className="text-xs text-destructive">{fieldErrors.password}</p>
                  )}
                </div>
              </>
            )}
            {sheetMode === 'edit' && editUser && (
              <>
                <p className="text-sm text-muted-foreground">{editUser.email}</p>
                <div className="space-y-2">
                  <Label htmlFor="u-edit-name">Full name</Label>
                  <Input
                    id="u-edit-name"
                    value={editFullName}
                    onChange={(e) => setEditFullName(e.target.value)}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="u-active"
                    checked={editActive}
                    onCheckedChange={(c) => setEditActive(c === true)}
                  />
                  <Label htmlFor="u-active">Active</Label>
                </div>
              </>
            )}
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Roles</legend>
              {roles.map((role) => (
                <div key={role.id} className="flex items-center gap-2">
                  <Checkbox
                    id={`role-${role.id}`}
                    checked={roleIds.has(role.id)}
                    onCheckedChange={(c) => {
                      setRoleIds((prev) => {
                        const next = new Set(prev)
                        if (c) next.add(role.id)
                        else next.delete(role.id)
                        return next
                      })
                    }}
                  />
                  <Label htmlFor={`role-${role.id}`}>{role.name}</Label>
                </div>
              ))}
              {fieldErrors.roles && (
                <p className="text-xs text-destructive">{fieldErrors.roles}</p>
              )}
            </fieldset>
        </div>
      </FormSheet>

      <ConfirmDialog
        open={confirmDeactivate !== null}
        title="Deactivate user"
        description={
          confirmDeactivate
            ? `Deactivate ${confirmDeactivate.email}? They will not be able to sign in.`
            : ''
        }
        confirmLabel="Deactivate"
        loading={deactivateMutation.isPending}
        onCancel={() => setConfirmDeactivate(null)}
        onConfirm={() => confirmDeactivate && deactivateMutation.mutate(confirmDeactivate)}
      />

      <Dialog
        open={confirmReset !== null}
        onOpenChange={(o) => {
          if (!o) {
            setConfirmReset(null)
            setResetPassword('')
          }
        }}
      >
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Reset password</DialogTitle>
            <DialogDescription>
              {confirmReset
                ? `Set a new password for ${confirmReset.email}. All active sessions will be revoked.`
                : ''}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="reset-pass">New password</Label>
            <Input
              id="reset-pass"
              type="password"
              value={resetPassword}
              onChange={(e) => setResetPassword(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setConfirmReset(null)
                setResetPassword('')
              }}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={resetMutation.isPending}
              onClick={() => {
                if (resetPassword.length < MIN_PASSWORD) {
                  toast.error(`Password must be at least ${MIN_PASSWORD} characters.`)
                  return
                }
                resetMutation.mutate()
              }}
            >
              Reset password
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
