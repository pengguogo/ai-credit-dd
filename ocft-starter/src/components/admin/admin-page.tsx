/**
 * 系统管理：角色列表 + 用户增改（仅管理员）。
 */
import { PlusIcon, RefreshCwIcon, ShieldIcon, UsersIcon } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MultiSelectField } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { ApiError, api, type SysRole } from '@/lib/api'
import type { AuthUser } from '@/lib/auth'
import { PERMISSION_OPTIONS, type PermissionCode } from '@/lib/permissions'
import { cn } from '@/lib/utils'

const DEFAULT_ROLE_PERMISSIONS: PermissionCode[] = ['workbench', 'catalog']
const PERMISSION_SELECT_OPTIONS = PERMISSION_OPTIONS.map((p) => ({
  value: p.code,
  label: p.label,
}))

type Tab = 'users' | 'roles'

export function AdminPage() {
  const [tab, setTab] = useState<Tab>('users')
  const [roles, setRoles] = useState<SysRole[]>([])
  const [users, setUsers] = useState<AuthUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    username: '',
    displayName: '',
    password: '',
    roleCode: 'account_manager',
  })
  const [saving, setSaving] = useState(false)
  const [roleForm, setRoleForm] = useState({
    code: '',
    name: '',
    description: '',
    permissions: [...DEFAULT_ROLE_PERMISSIONS] as PermissionCode[],
  })

  const reload = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [r, u] = await Promise.all([api.adminRoles(), api.adminUsers()])
      setRoles(r.roles)
      setUsers(u.users)
      if (r.roles.length && !r.roles.some((x) => x.code === form.roleCode)) {
        setForm((f) => ({ ...f, roleCode: r.roles[0].code }))
      }
    } catch (exc: unknown) {
      setError(exc instanceof ApiError ? exc.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [form.roleCode])

  useEffect(() => {
    void reload()
    // 首次加载
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const createUser = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.createUser({
        username: form.username.trim(),
        displayName: form.displayName.trim(),
        password: form.password,
        roleCode: form.roleCode,
      })
      setForm({ username: '', displayName: '', password: '', roleCode: form.roleCode })
      await reload()
    } catch (exc: unknown) {
      setError(exc instanceof ApiError ? exc.message : '创建用户失败')
    } finally {
      setSaving(false)
    }
  }

  const createRole = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.createRole({
        code: roleForm.code.trim(),
        name: roleForm.name.trim(),
        description: roleForm.description.trim(),
        permissions: roleForm.permissions,
      })
      setRoleForm({
        code: '',
        name: '',
        description: '',
        permissions: [...DEFAULT_ROLE_PERMISSIONS],
      })
      await reload()
    } catch (exc: unknown) {
      setError(exc instanceof ApiError ? exc.message : '创建角色失败')
    } finally {
      setSaving(false)
    }
  }

  const toggleStatus = async (user: AuthUser) => {
    setError('')
    try {
      await api.patchUser(user.id, { status: user.status === 'active' ? 'disabled' : 'active' })
      await reload()
    } catch (exc: unknown) {
      setError(exc instanceof ApiError ? exc.message : '更新失败')
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
      <header className="surface-panel rounded-xl px-5 py-4">
        <p className="font-mono text-[11px] font-medium tracking-wide text-brand uppercase">System Admin</p>
        <h1 className="mt-1 text-xl font-semibold tracking-tight">系统管理</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">管理登录角色与用户账号；密码只存哈希，不明文落库。</p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant={tab === 'users' ? 'default' : 'outline'}
          size="sm"
          className="cursor-pointer"
          onClick={() => setTab('users')}
        >
          <UsersIcon />用户
        </Button>
        <Button
          type="button"
          variant={tab === 'roles' ? 'default' : 'outline'}
          size="sm"
          className="cursor-pointer"
          onClick={() => setTab('roles')}
        >
          <ShieldIcon />角色
        </Button>
        <Button type="button" variant="ghost" size="sm" className="ml-auto cursor-pointer" onClick={() => void reload()}>
          {loading ? <Spinner /> : <RefreshCwIcon />}刷新
        </Button>
      </div>

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

      {tab === 'users' ? (
        <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
          <section className="surface-panel overflow-hidden rounded-xl">
            <div className="border-b border-border/70 px-4 py-3 text-sm font-medium">用户列表</div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">用户名</th>
                    <th className="px-3 py-2 font-medium">显示名</th>
                    <th className="px-3 py-2 font-medium">角色</th>
                    <th className="px-3 py-2 font-medium">状态</th>
                    <th className="px-3 py-2 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-t border-border/60">
                      <td className="px-3 py-2 font-mono">{u.username}</td>
                      <td className="px-3 py-2">{u.displayName}</td>
                      <td className="px-3 py-2">{u.roleName}<span className="ml-1 font-mono text-muted-foreground">({u.roleCode})</span></td>
                      <td className="px-3 py-2">
                        <span className={cn(
                          'rounded px-1.5 py-0.5 font-medium',
                          u.status === 'active' ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground',
                        )}>
                          {u.status === 'active' ? '启用' : '停用'}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <Button type="button" variant="outline" size="xs" className="cursor-pointer" onClick={() => void toggleStatus(u)}>
                          {u.status === 'active' ? '停用' : '启用'}
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {!loading && users.length === 0 && (
                    <tr><td colSpan={5} className="px-3 py-8 text-center text-muted-foreground">暂无用户</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <form className="surface-panel h-fit space-y-3 rounded-xl p-4" onSubmit={(e) => void createUser(e)}>
            <p className="text-sm font-medium">新建用户</p>
            <Field label="用户名">
              <Input value={form.username} required className="h-9 font-mono" onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </Field>
            <Field label="显示名">
              <Input value={form.displayName} className="h-9" onChange={(e) => setForm({ ...form, displayName: e.target.value })} />
            </Field>
            <Field label="密码">
              <Input type="password" value={form.password} required minLength={6} className="h-9" onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </Field>
            <Field label="角色">
              <select
                className="h-9 w-full rounded-lg border border-input bg-card px-2 text-sm"
                value={form.roleCode}
                onChange={(e) => setForm({ ...form, roleCode: e.target.value })}
              >
                {roles.map((r) => (
                  <option key={r.code} value={r.code}>{r.name} ({r.code})</option>
                ))}
              </select>
            </Field>
            <Button type="submit" className="w-full cursor-pointer" disabled={saving}>
              {saving ? <Spinner /> : <PlusIcon />}创建
            </Button>
          </form>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
          <section className="surface-panel overflow-hidden rounded-xl">
            <div className="border-b border-border/70 px-4 py-3 text-sm font-medium">角色列表</div>
            <ul className="divide-y divide-border/60">
              {roles.map((r) => (
                <li key={r.id} className="px-4 py-3 text-sm">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="font-medium">{r.name}</span>
                    <span className="font-mono text-xs text-muted-foreground">{r.code}</span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{r.description || '—'}</p>
                  <p className="mt-1 font-mono text-[11px] text-brand">{(r.permissions || []).join(' · ') || '无权限码'}</p>
                </li>
              ))}
            </ul>
          </section>

          <form className="surface-panel h-fit space-y-3 rounded-xl p-4" onSubmit={(e) => void createRole(e)}>
            <p className="text-sm font-medium">新建角色</p>
            <Field label="编码">
              <Input value={roleForm.code} required className="h-9 font-mono" onChange={(e) => setRoleForm({ ...roleForm, code: e.target.value })} />
            </Field>
            <Field label="名称">
              <Input value={roleForm.name} required className="h-9" onChange={(e) => setRoleForm({ ...roleForm, name: e.target.value })} />
            </Field>
            <Field label="说明">
              <Input value={roleForm.description} className="h-9" onChange={(e) => setRoleForm({ ...roleForm, description: e.target.value })} />
            </Field>
            <Field label="权限码">
              <MultiSelectField
                aria-label="权限码"
                values={roleForm.permissions}
                options={PERMISSION_SELECT_OPTIONS}
                placeholder="选择权限码"
                onValuesChange={(next) => {
                  const picked = new Set(next)
                  setRoleForm({
                    ...roleForm,
                    permissions: PERMISSION_OPTIONS
                      .map((p) => p.code)
                      .filter((code) => picked.has(code)),
                  })
                }}
              />
            </Field>
            <Button type="submit" className="w-full cursor-pointer" disabled={saving}>
              {saving ? <Spinner /> : <PlusIcon />}创建
            </Button>
          </form>
        </div>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}
