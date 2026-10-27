import brandLogo from '@/assets/logo-orange.svg'
import { Button } from '@/components/ui/button'
import { adminPath, homePath, reportHref, skillsPath, tablesPath, workspacePath } from '@/lib/app-route'
import type { AuthUser } from '@/lib/auth'
import { REPORT_DIMS } from '@/lib/report-dims'
import type { HealthReady } from '@/lib/types'
import { cn } from '@/lib/utils'

export type AppNavId = 'home' | 'tables' | 'workspace' | 'skills' | 'admin' | `report:${string}`

function HealthPill({ health }: { health: HealthReady | null }) {
  const state = !health ? 'checking' : health.status === 'ok' ? 'ok' : 'down'
  const text = state === 'checking' ? '检查后端…'
    : state === 'ok' ? `后端就绪 · ${health?.checks?.modelLock?.model ?? ''}`
      : `后端未就绪：${health?.reason ?? health?.checks?.llm?.status ?? '未知原因'}`
  return (
    <span
      role="status"
      className={cn(
        'inline-flex max-w-72 items-center gap-1.5 truncate rounded-md border px-2.5 py-1 font-mono text-[11px] font-medium tracking-wide',
        state === 'ok'
          ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-300'
          : state === 'down'
            ? 'border-red-400/40 bg-red-400/10 text-red-300'
            : 'border-slate-500/50 bg-slate-800/80 text-slate-400',
      )}
      title={text}
    >
      <span aria-hidden className="size-1.5 shrink-0 rounded-sm bg-current" />
      {text}
    </span>
  )
}

const MAIN_NAV: { id: AppNavId; label: string; href: string }[] = [
  { id: 'home', label: '智能尽调', href: homePath() },
  { id: 'tables', label: '企业档案', href: tablesPath() },
  { id: 'workspace', label: '贷款管理', href: workspacePath() },
]

function reportNavItems(): { id: AppNavId; label: string; href: string }[] {
  return REPORT_DIMS.filter((d) => d.slug !== 'report').map((d) => ({
    id: `report:${d.slug}`,
    label: d.label,
    href: reportHref(d.slug),
  }))
}

export function AppHeader({ health, user, canWorkbench, canCatalog, canApplications, canDdSteps, canConfirm, isAdmin, title, activeNav, onNavigate, onLogout, workspaceHref = workspacePath() }: {
  health: HealthReady | null
  user: AuthUser
  canWorkbench: boolean
  canCatalog: boolean
  canApplications: boolean
  canDdSteps: boolean
  canConfirm: boolean
  isAdmin: boolean
  title: string
  activeNav: AppNavId
  onNavigate: (href: string) => void
  onLogout: () => void
  /** 贷款管理入口：按权限落到第一个可见子页 */
  workspaceHref?: string
}) {
  // 只读：智能尽调 + 尽调维度；企业档案与贷款管理仅审批/管理角色
  const mainNav = MAIN_NAV.filter((item) => {
    if (item.id === 'home') return canWorkbench
    if (item.id === 'tables') return canCatalog && canApplications
    if (item.id === 'workspace') return canConfirm || canApplications
    return true
  }).map((item) => (item.id === 'workspace' ? { ...item, href: workspaceHref } : item))
  return (
    <header className="app-header z-40 shrink-0">
      <div className="flex h-12 w-full items-center gap-3 px-4 lg:px-6 xl:px-8">
        <img src={brandLogo} alt="金融壹账通" className="h-6 w-auto shrink-0" />
        <span className="hidden h-4 w-px bg-slate-500/60 sm:block" aria-hidden />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold leading-tight tracking-tight text-slate-50">{title}</p>
          <p className="hidden truncate font-mono text-[10px] tracking-wide text-brand sm:block">
            尽调 Agent · 实时取证
          </p>
        </div>
        <div className="ml-auto flex min-w-0 items-center gap-3">
          <HealthPill health={health} />
          <div className="hidden min-w-0 text-right sm:block">
            <p className="truncate text-xs font-medium text-slate-100">
              {user.displayName || user.username}
            </p>
            <p className="truncate font-mono text-[10px] text-slate-400">
              {user.displayName === user.roleName
                ? user.username
                : `${user.username} · ${user.roleName}`}
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="xs"
            className="cursor-pointer border-slate-500/50 bg-slate-900/40 text-slate-200 hover:bg-slate-800 hover:text-white"
            onClick={onLogout}
          >
            退出
          </Button>
        </div>
      </div>
      <div className="app-nav-strip">
        <div className="flex w-full items-stretch gap-3 overflow-x-auto px-4 lg:px-6 xl:px-8">
          {mainNav.length > 0 && (
            <NavGroup
              label="工作区"
              items={mainNav}
              activeNav={activeNav}
              onNavigate={onNavigate}
            />
          )}
          {canDdSteps && (
            <>
              {mainNav.length > 0 && <span className="my-2 w-px shrink-0 bg-slate-600/70" aria-hidden />}
              <NavGroup
                label="尽调维度"
                items={reportNavItems()}
                activeNav={activeNav}
                onNavigate={onNavigate}
              />
            </>
          )}
          <span className="my-2 w-px shrink-0 bg-slate-600/70" aria-hidden />
          <NavGroup
            label="Agent 能力"
            items={[{ id: 'skills', label: 'Agent 技能中心', href: skillsPath() }]}
            activeNav={activeNav}
            onNavigate={onNavigate}
          />
          {isAdmin && (
            <>
              <span className="my-2 w-px shrink-0 bg-slate-600/70" aria-hidden />
              <NavGroup
                label="系统"
                items={[{ id: 'admin', label: '系统管理', href: adminPath() }]}
                activeNav={activeNav}
                onNavigate={onNavigate}
              />
            </>
          )}
        </div>
      </div>
    </header>
  )
}

function NavGroup({ label, items, activeNav, onNavigate }: {
  label: string
  items: { id: AppNavId; label: string; href: string }[]
  activeNav: AppNavId
  onNavigate: (href: string) => void
}) {
  return (
    <nav aria-label={label} className="flex h-11 shrink-0 items-stretch gap-0.5">
      {items.map((item) => {
        const active = activeNav === item.id
        return (
          <a
            key={item.id}
            href={item.href}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'relative flex shrink-0 items-center px-2.5 text-sm whitespace-nowrap transition-colors sm:px-3',
              active
                ? 'font-semibold text-brand'
                : 'text-slate-400 hover:text-slate-100',
            )}
            onClick={(e) => {
              e.preventDefault()
              onNavigate(item.href)
            }}
          >
            {item.label}
            {active && (
              <span
                aria-hidden
                className="absolute inset-x-1.5 bottom-0 h-0.5 bg-brand"
              />
            )}
          </a>
        )
      })}
    </nav>
  )
}
