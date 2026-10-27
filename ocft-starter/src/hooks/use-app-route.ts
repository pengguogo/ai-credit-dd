import { useEffect, useSyncExternalStore } from 'react'

import {
  navigate,
  parsePath,
  pathForRoute,
  tablesPath,
  type AppRoute,
} from '@/lib/app-route'
import { LIST_TABLES } from '@/lib/catalog-tables'
import { reportPath, type ReportDim } from '@/lib/report-dims'

function subscribe(onStoreChange: () => void): () => void {
  window.addEventListener('popstate', onStoreChange)
  return () => window.removeEventListener('popstate', onStoreChange)
}

function getSnapshot(): string {
  return window.location.pathname + window.location.search
}

function getServerSnapshot(): string {
  return '/'
}

function normalizePath(pathname: string): string {
  return pathname.replace(/\/+$/, '') || '/'
}

export function useAppRoute(): {
  route: AppRoute
  /** 当前 location 的查询串（含前导 ?）；贷款管理-尽调报告用 applicationId 过滤 */
  search: string
  goHome: () => void
  goTables: (table?: string) => void
  goReport: (slug?: ReportDim['slug']) => void
} {
  const location = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
  const queryIndex = location.indexOf('?')
  const pathname = queryIndex === -1 ? location : location.slice(0, queryIndex)
  const search = queryIndex === -1 ? '' : location.slice(queryIndex)
  const route = parsePath(pathname)

  useEffect(() => {
    const current = normalizePath(pathname)
    const canonical = pathForRoute(parsePath(pathname))
    if (current !== canonical) {
      // 规范化路径时保留企业/申请 query，避免切换或纠正 slug 时丢失上下文
      navigate(`${canonical}${window.location.search}`, true)
    }
  }, [pathname])

  return {
    route,
    search,
    goHome: () => navigate('/'),
    goTables: (table = LIST_TABLES[0].table) => navigate(tablesPath(table)),
    goReport: (slug?: ReportDim['slug']) => navigate(reportPath(slug)),
  }
}

export function useDocumentTitle(route: AppRoute, scenarioName: string): void {
  let label: string | null = null
  if (route.page === 'tables') label = `${route.table.label} · 企业档案`
  if (route.page === 'report') label = `${route.dim.label} · 尽调维度`
  if (route.page === 'workspace') label = `${route.section === 'reports' ? '尽调报告' : '贷款申请'} · 贷款管理`
  if (route.page === 'skills') label = 'Agent Skill 技能中心'
  if (route.page === 'admin') label = '系统管理'
  if (route.page === 'login') label = '登录'
  useEffect(() => {
    if (label) {
      document.title = `${label} · ${scenarioName} · 金融壹账通`
      return
    }
    document.title = `${scenarioName} · 金融壹账通`
  }, [label, scenarioName])
}

export function navIdFromRoute(route: AppRoute): import('@/components/app-header').AppNavId {
  if (route.page === 'tables') return 'tables'
  if (route.page === 'workspace') return 'workspace'
  if (route.page === 'skills') return 'skills'
  if (route.page === 'report') return `report:${route.dim.slug}`
  if (route.page === 'admin') return 'admin'
  return 'home'
}
