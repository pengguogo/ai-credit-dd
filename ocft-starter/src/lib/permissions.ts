/** 前端菜单/按钮可见性：与后端 DEMO_ROLES 权限码对齐。 */
import { hasPermission, type AuthUser } from '@/lib/auth'
import type { LoanSection } from '@/lib/app-route'
import { LIST_TABLES, type ListTableItem } from '@/lib/catalog-tables'

export type PermissionCode =
  | 'admin'
  | 'workbench'
  | 'dd_steps'
  | 'catalog'
  | 'applications'
  | 'confirm'
  | 'catalog_write'

/** 系统管理「新建角色」等多选下拉的可选项（与后端权限码一致）。 */
export const PERMISSION_OPTIONS: ReadonlyArray<{ code: PermissionCode; label: string }> = [
  { code: 'admin', label: '系统管理' },
  { code: 'workbench', label: '智能尽调' },
  { code: 'dd_steps', label: '尽调1–5步' },
  { code: 'catalog', label: '数据目录' },
  { code: 'applications', label: '审批表' },
  { code: 'confirm', label: '确认/驳回' },
  { code: 'catalog_write', label: '数据写' },
]

export function can(user: AuthUser | null | undefined, code: PermissionCode): boolean {
  return hasPermission(user, code)
}

/** 企业档案可见表：viewer 仅企业信息；有 applications 时另含其余表。贷款申请已移到「贷款管理」。 */
export function visibleListTables(user: AuthUser | null | undefined): ListTableItem[] {
  if (!can(user, 'catalog')) return []
  if (can(user, 'applications')) return LIST_TABLES.filter((t) => t.kind !== 'applications')
  return LIST_TABLES.filter((t) => t.kind === 'enterprises')
}

/** 贷款管理可见子页：贷款申请需 applications，尽调报告需 confirm。 */
export function visibleLoanSections(user: AuthUser | null | undefined): LoanSection[] {
  const sections: LoanSection[] = []
  if (can(user, 'catalog') && can(user, 'applications')) sections.push('applications')
  if (can(user, 'confirm')) sections.push('reports')
  return sections
}
