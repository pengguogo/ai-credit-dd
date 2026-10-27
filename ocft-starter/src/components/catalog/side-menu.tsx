/** 页面左侧竖排子菜单：企业档案（业务表）与贷款管理（贷款申请 / 尽调报告）共用。 */
import { cn } from '@/lib/utils'

export function SideMenu({ label, items, activeId, onPick }: {
  label: string
  items: { id: string; label: string; href: string }[]
  activeId: string
  onPick: (id: string) => void
}) {
  return (
    <aside className="surface-panel flex h-full flex-col rounded-xl">
      <nav aria-label={label} className="min-h-0 flex-1 overflow-y-auto p-2">
        <ul className="flex flex-col gap-0.5">
          {items.map((item) => {
            const active = item.id === activeId
            return (
              <li key={item.id}>
                <a
                  href={item.href}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'block cursor-pointer rounded-lg px-3 py-2.5 pr-5 text-sm whitespace-nowrap transition-colors',
                    active
                      ? 'bg-brand-soft font-medium text-brand'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )}
                  onClick={(e) => {
                    e.preventDefault()
                    onPick(item.id)
                  }}
                >
                  {item.label}
                </a>
              </li>
            )
          })}
        </ul>
      </nav>
    </aside>
  )
}
