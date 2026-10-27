/**
 * 贷款管理：左侧子菜单切换「贷款申请」与「尽调报告」。
 * 贷款申请复用企业档案的表格页（导入、增删改沿用原权限）；尽调报告即原报告列表页。
 */
import { DataListPage } from '@/components/catalog/data-list-page'
import { SideMenu } from '@/components/catalog/side-menu'
import { WorkspacePage } from '@/components/workspace/workspace-page'
import { LOAN_SECTIONS, workspacePath, type LoanSection } from '@/lib/app-route'
import { LIST_TABLES } from '@/lib/catalog-tables'

const APPLICATIONS_TABLE = LIST_TABLES.find((item) => item.kind === 'applications')!

export function LoanPage({ actorId, section, sections, allowWrite, allowReview, applicationId, onNavigate }: {
  actorId: string
  section: LoanSection
  /** 按权限过滤后的可见子页 */
  sections: LoanSection[]
  allowWrite: boolean
  /** 贷款申请的人工审核（confirm 权限） */
  allowReview: boolean
  /** 尽调报告页的贷款编号过滤（从智能尽调「查看报告」跳转） */
  applicationId?: string
  onNavigate: (href: string) => void
}) {
  const menu = (
    <SideMenu
      label="贷款管理菜单"
      items={LOAN_SECTIONS.filter((item) => sections.includes(item.section))
        .map((item) => ({ id: item.section, label: item.label, href: workspacePath(item.section) }))}
      activeId={section}
      onPick={(id) => onNavigate(workspacePath(id as LoanSection))}
    />
  )

  if (section === 'applications') {
    return (
      <DataListPage
        actorId={actorId}
        table={APPLICATIONS_TABLE}
        tables={[APPLICATIONS_TABLE]}
        allowWrite={allowWrite}
        allowReview={allowReview}
        onNavigate={onNavigate}
        menu={menu}
      />
    )
  }
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[9.5rem_minmax(0,1fr)]">
      {menu}
      <div className="flex min-h-0 min-w-0 flex-col">
        <WorkspacePage
          actorId={actorId}
          applicationId={applicationId}
          onClearApplication={() => onNavigate(workspacePath('reports'))}
        />
      </div>
    </div>
  )
}
