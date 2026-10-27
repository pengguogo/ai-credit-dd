/** 轻量路径路由：智能尽调、企业档案、贷款管理、尽调单维度、技能中心、系统管理、登录。不引入 react-router。 */
import { LIST_TABLES, type ListTableItem } from '@/lib/catalog-tables'
import { REPORT_DIMS, dimBySlug, reportHref, reportPath, type ReportDim } from '@/lib/report-dims'

export type AppRoute =
  | { page: 'home' }
  | { page: 'tables'; table: ListTableItem }
  | { page: 'report'; dim: ReportDim }
  | { page: 'workspace'; section: LoanSection }
  | { page: 'skills' }
  | { page: 'admin' }
  | { page: 'login' }

/** 贷款管理子菜单：贷款申请 / 尽调报告 */
export type LoanSection = 'applications' | 'reports'

export const LOAN_SECTIONS: { section: LoanSection; label: string }[] = [
  { section: 'applications', label: '贷款申请' },
  { section: 'reports', label: '尽调报告' },
]

export function homePath(): string {
  return '/'
}

export function tablesPath(table = LIST_TABLES[0].table): string {
  return `/tables/${table}`
}

export function workspacePath(section: LoanSection = 'applications'): string {
  return `/workspace/${section}`
}

/** 跳到「贷款管理-尽调报告」并按贷款编号筛选出对应的尽调报告。 */
export function workspaceReportHref(applicationId: string): string {
  return `${workspacePath('reports')}?applicationId=${encodeURIComponent(applicationId)}`
}

export function skillsPath(): string {
  return '/skills'
}

export function adminPath(): string {
  return '/admin'
}

export function loginPath(): string {
  return '/login'
}

export function tableBySlug(slug: string | undefined): ListTableItem {
  return LIST_TABLES.find((item) => item.table === slug) ?? LIST_TABLES[0]
}

export function parsePath(pathname: string): AppRoute {
  const path = pathname.replace(/\/+$/, '') || '/'
  if (path === '/login') return { page: 'login' }
  if (path === '/admin') return { page: 'admin' }
  if (path === '/skills') return { page: 'skills' }
  if (path === '/workspace') return { page: 'workspace', section: 'applications' }
  const workspace = path.match(/^\/workspace\/([^/]+)$/)
  if (workspace) {
    return { page: 'workspace', section: workspace[1] === 'reports' ? 'reports' : 'applications' }
  }
  if (path === '/' || path === '') return { page: 'home' }
  if (path === '/tables') return { page: 'tables', table: LIST_TABLES[0] }
  const tables = path.match(/^\/tables\/([^/]+)$/)
  if (tables) return { page: 'tables', table: tableBySlug(tables[1]) }
  if (path === '/report') return { page: 'report', dim: REPORT_DIMS[0] }
  const report = path.match(/^\/report\/([^/]+)$/)
  if (report) return { page: 'report', dim: dimBySlug(report[1]) }
  return { page: 'home' }
}

export function pathForRoute(route: AppRoute): string {
  if (route.page === 'home') return homePath()
  if (route.page === 'tables') return tablesPath(route.table.table)
  if (route.page === 'workspace') return workspacePath(route.section)
  if (route.page === 'skills') return skillsPath()
  if (route.page === 'admin') return adminPath()
  if (route.page === 'login') return loginPath()
  return reportPath(route.dim.slug)
}

export function navigate(to: string, replace = false): void {
  const method = replace ? 'replaceState' : 'pushState'
  window.history[method](null, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export { reportPath, reportHref }
