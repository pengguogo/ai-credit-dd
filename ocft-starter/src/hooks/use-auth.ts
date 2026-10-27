/** 登录态钩子：校验 /me、登录、登出。 */
import { useCallback, useEffect, useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { readSession, writeSession, type AuthSession, type AuthUser } from '@/lib/auth'
import { can } from '@/lib/permissions'

export function useAuth() {
  const initial = readSession()
  const [session, setSession] = useState<AuthSession | null>(() => initial)
  const [booting, setBooting] = useState(() => Boolean(initial))
  const [error, setError] = useState('')

  useEffect(() => {
    if (!initial) return
    let cancelled = false
    api.me()
      .then((body) => {
        if (cancelled) return
        const next = { token: initial.token, user: body.user }
        writeSession(next)
        setSession(next)
        setError('')
      })
      .catch((exc: unknown) => {
        if (cancelled) return
        writeSession(null)
        setSession(null)
        if (!(exc instanceof ApiError && exc.status === 401)) {
          setError(exc instanceof ApiError ? exc.message : '会话校验失败')
        }
      })
      .finally(() => {
        if (!cancelled) setBooting(false)
      })
    return () => {
      cancelled = true
    }
    // 仅挂载时校验本地会话
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    setError('')
    const body = await api.login(username, password)
    const next = { token: body.token, user: body.user }
    writeSession(next)
    setSession(next)
    return next
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      // 本地清会话即可
    }
    writeSession(null)
    setSession(null)
  }, [])

  const user: AuthUser | null = session?.user ?? null
  return {
    booting,
    session,
    user,
    error,
    isAdmin: can(user, 'admin'),
    canWorkbench: can(user, 'workbench'),
    canDdSteps: can(user, 'dd_steps'),
    canCatalog: can(user, 'catalog'),
    canApplications: can(user, 'applications'),
    canConfirm: can(user, 'confirm'),
    canCatalogWrite: can(user, 'catalog_write'),
    login,
    logout,
  }
}
