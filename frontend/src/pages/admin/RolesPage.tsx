import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LockIcon, ShieldIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/api/errors'
import { createRole, listPermissions, listRoles, replaceRolePermissions } from '@/api/roles'
import type { RoleOut } from '@/api/types'
import { FormSheet } from '@/components/layout/FormSheet'
import { IconChip } from '@/components/layout/IconChip'
import { EmptyState } from '@/components/layout/EmptyState'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  ADMIN_ROLE_NAME,
  permissionGroupChipLabel,
} from '@/lib/permissions'
import {
  groupPermissionsByArea,
  PERMISSION_AREA_LABELS,
  permissionLabel,
  type PermissionArea,
} from '@/lib/permissionLabels'

const MAX_CHIPS = 3
const CHIP_TONES = ['sky', 'amber', 'teal', 'rose'] as const

export function RolesPage() {
  const queryClient = useQueryClient()
  const rolesQuery = useQuery({ queryKey: ['roles'], queryFn: listRoles })
  const permissionsQuery = useQuery({ queryKey: ['permissions'], queryFn: listPermissions })

  const [createOpen, setCreateOpen] = useState(false)
  const [editRole, setEditRole] = useState<RoleOut | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [permSearch, setPermSearch] = useState('')

  const allCodes = useMemo(
    () => permissionsQuery.data?.map((p) => p.code) ?? [],
    [permissionsQuery.data],
  )

  const grouped = useMemo(() => groupPermissionsByArea(allCodes), [allCodes])

  const filteredGroups = useMemo(() => {
    const q = permSearch.trim().toLowerCase()
    if (!q) return grouped
    const next = new Map<PermissionArea, string[]>()
    for (const [area, codes] of grouped) {
      const hits = codes.filter(
        (c) =>
          c.includes(q) ||
          permissionLabel(c).toLowerCase().includes(q) ||
          PERMISSION_AREA_LABELS[area].toLowerCase().includes(q),
      )
      if (hits.length) next.set(area, hits)
    }
    return next
  }, [grouped, permSearch])

  const createMutation = useMutation({
    mutationFn: () =>
      createRole({
        name: name.trim(),
        description: description.trim() || null,
        permission_codes: [...selected],
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['roles'] })
      setCreateOpen(false)
      resetForm()
      toast.success('Role created.')
    },
    onError: (err: unknown) => {
      toast.error(err instanceof ApiError ? err.displayMessage() : 'Could not create role.')
    },
  })

  const updateMutation = useMutation({
    mutationFn: (roleId: string) =>
      replaceRolePermissions(roleId, { permission_codes: [...selected] }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['roles'] })
      setEditRole(null)
      toast.success('Permissions updated.')
    },
    onError: (err: unknown) => {
      toast.error(err instanceof ApiError ? err.displayMessage() : 'Could not update role.')
    },
  })

  function resetForm() {
    setName('')
    setDescription('')
    setSelected(new Set())
    setPermSearch('')
  }

  function openCreate() {
    resetForm()
    setCreateOpen(true)
  }

  function openEdit(role: RoleOut) {
    if (role.name === ADMIN_ROLE_NAME) return
    setEditRole(role)
    setSelected(new Set(role.permissions))
    setPermSearch('')
  }

  function toggleGroup(codes: string[], checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev)
      for (const code of codes) {
        if (checked) next.add(code)
        else next.delete(code)
      }
      return next
    })
  }

  function permissionChips(role: RoleOut) {
    const groups = groupPermissionsByArea(role.permissions)
    const entries = [...groups.entries()]
    const visible = entries.slice(0, MAX_CHIPS)
    const extra = entries.length - visible.length
    return { visible, extra }
  }

  const sheetOpen = createOpen || editRole !== null
  const readOnly = editRole?.name === ADMIN_ROLE_NAME

  function closeSheet() {
    setCreateOpen(false)
    setEditRole(null)
  }

  if (rolesQuery.isPending || permissionsQuery.isPending) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-48" />
        ))}
      </div>
    )
  }

  if (rolesQuery.isError) {
    return <p className="text-destructive text-sm">Failed to load roles.</p>
  }

  const roles = rolesQuery.data ?? []

  return (
    <div>
      <PageHeader
        title="Roles"
        description="Permission bundles assigned to users."
        action={
          <Button type="button" onClick={openCreate}>
            Create role
          </Button>
        }
      />

      {roles.length === 0 ? (
        <EmptyState
          title="No roles"
          description="Create a role to define a permission bundle."
          action={
            <Button type="button" onClick={openCreate}>
              Create role
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {roles.map((role, index) => {
            const builtIn = role.name === ADMIN_ROLE_NAME
            const { visible, extra } = permissionChips(role)
            const tone = CHIP_TONES[index % CHIP_TONES.length]
            return (
              <Card key={role.id} className="flex min-h-[220px] flex-col shadow-card">
                <CardHeader>
                  <div className="flex items-start gap-3">
                    <IconChip icon={ShieldIcon} tone={tone} size="sm" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <CardTitle className="text-base">{role.name}</CardTitle>
                        {builtIn && <Badge variant="secondary">Built-in</Badge>}
                      </div>
                      {role.description ? (
                        <CardDescription className="mt-2 line-clamp-2">
                          {role.description}
                        </CardDescription>
                      ) : (
                        <CardDescription className="mt-2">No description</CardDescription>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="flex-1 space-y-2">
                  <p className="text-xs text-muted-foreground">
                    {role.permissions.length} permission
                    {role.permissions.length === 1 ? '' : 's'}
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {visible.map(([area, codes]) => (
                      <Badge key={area} variant="outline" className="bg-secondary/50">
                        {permissionGroupChipLabel(area, codes.length)}
                      </Badge>
                    ))}
                    {extra > 0 && <Badge variant="outline">+{extra} more</Badge>}
                  </div>
                </CardContent>
                <CardFooter className="mt-auto border-t border-border pt-4">
                  {builtIn ? (
                    <p className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                      <LockIcon className="size-3.5" aria-hidden />
                      System role
                    </p>
                  ) : (
                    <Button variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => openEdit(role)}>
                      Edit permissions
                    </Button>
                  )}
                </CardFooter>
              </Card>
            )
          })}
        </div>
      )}

      <FormSheet
        open={sheetOpen}
        onOpenChange={(o) => !o && closeSheet()}
        title={
          editRole ? `Edit — ${editRole.name}` : createOpen ? 'Create role' : 'Role'
        }
        description={
          createOpen
            ? 'Name the role and choose permissions.'
            : editRole
              ? 'Update permissions for this role.'
              : undefined
        }
        hideFooter={readOnly}
        footer={
          <>
            <Button type="button" variant="outline" onClick={closeSheet}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={createMutation.isPending || updateMutation.isPending}
              onClick={() => {
                if (editRole) updateMutation.mutate(editRole.id)
                else if (name.trim()) createMutation.mutate()
              }}
            >
              Save
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {createOpen && (
            <>
              <div className="space-y-2">
                <Label htmlFor="role-name">Name</Label>
                <Input id="role-name" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="role-desc">Description</Label>
                <Input
                  id="role-desc"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
            </>
          )}
          {readOnly ? (
            <p className="text-sm text-muted-foreground">The Admin role cannot be modified.</p>
          ) : (
            <>
              <Input
                placeholder="Search permissions…"
                value={permSearch}
                onChange={(e) => setPermSearch(e.target.value)}
              />
              <div className="space-y-4">
                {[...filteredGroups.entries()].map(([area, codes]) => {
                  const allOn = codes.every((c) => selected.has(c))
                  const someOn = codes.some((c) => selected.has(c))
                  return (
                    <fieldset
                      key={area}
                      className="space-y-2 rounded-lg border border-border p-3"
                    >
                      <div className="flex items-center gap-2">
                        <Checkbox
                          id={`group-${area}`}
                          checked={allOn ? true : someOn ? 'indeterminate' : false}
                          onCheckedChange={(c) => toggleGroup(codes, c === true)}
                        />
                        <Label htmlFor={`group-${area}`} className="text-sm font-semibold">
                          {PERMISSION_AREA_LABELS[area]}
                        </Label>
                      </div>
                      <ul className="space-y-2 pl-6">
                        {codes.map((code) => (
                          <li key={code} className="flex items-center gap-2">
                            <Checkbox
                              id={code}
                              checked={selected.has(code)}
                              onCheckedChange={(c) => {
                                setSelected((prev) => {
                                  const next = new Set(prev)
                                  if (c) next.add(code)
                                  else next.delete(code)
                                  return next
                                })
                              }}
                            />
                            <Label htmlFor={code} className="text-sm font-normal">
                              {permissionLabel(code)}
                            </Label>
                          </li>
                        ))}
                      </ul>
                    </fieldset>
                  )
                })}
              </div>
            </>
          )}
        </div>
      </FormSheet>
    </div>
  )
}
