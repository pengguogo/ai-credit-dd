/** 登录会话：token + 用户信息，存 localStorage。 */

export type AuthUser = {
  id: number
  username: string
  displayName: string
  status: string
  roleCode: string
  roleName: string
  permissions: string[]
}

export type AuthSession = {
  token: string
  user: AuthUser
}

const KEY = 'ocft.auth.session'

export function readSession(): AuthSession | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as AuthSession
    if (!parsed?.token || !parsed?.user?.username) return null
    return parsed
  } catch {
    return null
  }
}

export function writeSession(session: AuthSession | null): void {
  if (!session) {
    localStorage.removeItem(KEY)
    return
  }
  localStorage.setItem(KEY, JSON.stringify(session))
}

export function hasPermission(user: AuthUser | null | undefined, code: string): boolean {
  if (!user) return false
  if (user.roleCode === 'admin') return true
  return (user.permissions ?? []).includes(code)
}
