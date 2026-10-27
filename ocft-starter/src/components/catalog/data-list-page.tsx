/** 企业档案页：按表浏览；可写表支持导入与增删改；尽调维度只读关系图。 */
import { ClipboardCheckIcon, DatabaseIcon, PencilIcon, PlusIcon, SearchIcon, Trash2Icon, XIcon } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'

import { CsvImportDialog } from '@/components/catalog/csv-import-dialog'
import { RecordFormDialog } from '@/components/catalog/record-form-dialog'
import { ReviewDialog, type ReviewTarget } from '@/components/catalog/review-dialog'
import { SchemaFlow } from '@/components/catalog/schema-flow'
import { SideMenu } from '@/components/catalog/side-menu'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { SCENARIO_ID } from '@/data/scenario'
import { ApiError, api } from '@/lib/api'
import { tablesPath } from '@/lib/app-route'
import { LIST_TABLES, type CatalogKind, type ListTableItem } from '@/lib/catalog-tables'
import type { Catalog } from '@/lib/types'

type WritableKind = Exclude<CatalogKind, 'schema_relationships'>

function cellText(key: string, value: string | number | null): string {
  if (value == null || value === '') return '—'
  if (key === 'status') {
    if (value === 'pending') return '待处理'
    if (value === 'pending_review') return '待审核'
    if (value === 'approved') return '审核通过'
    if (value === 'rejected') return '审核不通过'
  }
  if (typeof value === 'number') return value.toLocaleString('zh-CN')
  return String(value)
}

function countLabel(data: Catalog): string {
  if (!data.query) return `共 ${data.total} 条`
  if (data.matched > data.rows.length) {
    return `显示前 ${data.rows.length} 条，匹配 ${data.matched} 条，全表 ${data.total} 条`
  }
  return `匹配 ${data.matched} 条，全表 ${data.total} 条`
}

/** 尽调维度计数：维度为关系两端去重，关联为有效关系行数 */
function schemaCountLabel(data: Catalog): string {
  const edges = data.rows.filter((row) => row.mainTable && row.childTable)
  const dims = new Set(edges.flatMap((row) => [String(row.mainTable), String(row.childTable)]))
  return `${dims.size} 个维度 · ${edges.length} 条关联`
}

export function DataListPage({ actorId, table, onNavigate, tables = LIST_TABLES, allowWrite = true, allowReview = false, menu }: {
  actorId: string
  table: ListTableItem
  onNavigate: (href: string) => void
  /** 按角色过滤后的可见表 */
  tables?: ListTableItem[]
  allowWrite?: boolean
  /** 贷款申请的人工审核：需 confirm 权限，与是否可写数据相互独立 */
  allowReview?: boolean
  /** 替换左侧菜单（贷款管理复用本页展示贷款申请） */
  menu?: ReactNode
}) {
  const [data, setData] = useState<Catalog | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState('')
  const [keyword, setKeyword] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [form, setForm] = useState<{ mode: 'create' | 'edit'; row: Record<string, string | number | null> | null } | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [reviewTarget, setReviewTarget] = useState<ReviewTarget | null>(null)
  const kind = table.kind
  const isSchema = kind === 'schema_relationships'
  const writable = allowWrite && table.writable
  const reviewable = allowReview && kind === 'applications'
  const showActions = writable || reviewable

  useEffect(() => {
    const next = draft.trim()
    const timer = setTimeout(() => {
      setKeyword((prev) => {
        if (prev !== next) setLoading(true)
        return next
      })
    }, 300)
    return () => clearTimeout(timer)
  }, [draft])

  useEffect(() => {
    let cancelled = false
    api.catalog(actorId, SCENARIO_ID, keyword, kind)
      .then((body) => {
        if (cancelled) return
        setData(body)
        setError('')
      })
      .catch((exc: unknown) => {
        if (cancelled) return
        setData(null)
        setError(exc instanceof ApiError ? exc.message : '业务表加载失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [actorId, keyword, kind, reloadKey])

  const searchNow = () => {
    const next = draft.trim()
    setKeyword((prev) => {
      if (prev !== next) setLoading(true)
      return next
    })
  }

  const clearFilter = () => {
    setDraft('')
    setKeyword((prev) => {
      if (prev !== '') setLoading(true)
      return ''
    })
  }

  const pickTable = (next: ListTableItem) => {
    if (next.table === table.table) return
    setDraft('')
    setKeyword('')
    setData(null)
    setLoading(true)
    setForm(null)
    setReviewTarget(null)
    onNavigate(tablesPath(next.table))
  }

  const refresh = () => {
    setLoading(true)
    setReloadKey((k) => k + 1)
  }

  const removeRow = async (id: number) => {
    if (!writable || isSchema) return
    if (!window.confirm('确认删除这条记录？此操作不可撤销。')) return
    setDeletingId(id)
    setError('')
    try {
      await api.deleteCatalogRecord(actorId, SCENARIO_ID, kind, id)
      refresh()
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '删除失败')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[9.5rem_minmax(0,1fr)]">
      {menu ?? (
        <SideMenu
          label="业务表菜单"
          items={tables.map((item) => ({ id: item.table, label: item.label, href: tablesPath(item.table) }))}
          activeId={table.table}
          onPick={(id) => {
            const next = tables.find((item) => item.table === id)
            if (next) pickTable(next)
          }}
        />
      )}

      <Card className="flex h-full min-w-0 flex-col">
        <CardHeader className="border-b border-border/70 bg-tech-soft/35">
          <div className="flex flex-wrap items-start justify-between gap-2">
            {isSchema ? (
              // 尽调维度：标题、说明与计数合为一行
              <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
                <CardTitle className="text-base tracking-tight">{table.label}</CardTitle>
                <p className="min-w-0 flex-1 text-xs text-muted-foreground">
                  企业档案按尽调维度归集，以企业为中心关联；点击连线或节点查看说明。
                </p>
                {data && <p className="font-mono text-[11px] text-muted-foreground">{schemaCountLabel(data)}</p>}
              </div>
            ) : (
              <div className="min-w-0">
                <CardTitle className="text-base tracking-tight">{table.label}</CardTitle>
                <p className="text-xs text-muted-foreground">{data?.note ?? '加载中…'}</p>
              </div>
            )}
            {writable && table.csvFile && (
              <div className="flex flex-wrap items-center gap-1.5">
                <CsvImportDialog
                  actorId={actorId}
                  allowedFileName={table.csvFile}
                  onImported={refresh}
                />
                <Button type="button" size="sm" onClick={() => setForm({ mode: 'create', row: null })}>
                  <PlusIcon />新增
                </Button>
              </div>
            )}
          </div>
          {!isSchema && (
            <>
              <div className="mt-2 flex items-center overflow-hidden rounded-lg border border-input bg-card shadow-sm focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
                <label htmlFor="data-list-filter" className="sr-only">筛选</label>
                <Input
                  id="data-list-filter"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      searchNow()
                    }
                    if (e.key === 'Escape' && draft) {
                      e.preventDefault()
                      clearFilter()
                    }
                  }}
                  placeholder={
                    kind === 'applications'
                      ? '编号 / 企业 / 用途，或状态：待处理、待审核、审核通过、审核不通过'
                      : '按编号或关键字筛选'
                  }
                  className="h-9 rounded-none border-0 bg-transparent text-xs shadow-none focus-visible:ring-0"
                />
                {draft && (
                  <Button type="button" variant="ghost" className="h-9 cursor-pointer rounded-none px-2" aria-label="清空" onClick={clearFilter}>
                    <XIcon />
                  </Button>
                )}
                <Button type="button" variant="ghost" className="h-9 cursor-pointer rounded-none border-l px-3" aria-label="搜索" onClick={searchNow}>
                  {loading ? <Spinner /> : <SearchIcon />}
                </Button>
              </div>
              {data && <p className="mt-1.5 text-[11px] text-muted-foreground">{countLabel(data)}</p>}
            </>
          )}
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col overflow-hidden p-3">
          {loading && !data && (
            <p className="flex items-center gap-2 px-1 py-3 text-sm text-muted-foreground">
              <Spinner /> 读取业务表…
            </p>
          )}
          {!loading && error && (
            <p role="alert" className="px-1 py-3 text-sm text-destructive">{error}</p>
          )}
          {isSchema && data && (
            <SchemaFlow rows={data.rows as Array<{
              mainTable?: string | number | null
              childTable?: string | number | null
              primaryKey?: string | number | null
              foreignKey?: string | number | null
              note?: string | number | null
            }>} />
          )}
          {!isSchema && data && data.total === 0 && (
            <Empty className="h-full border border-dashed">
              <EmptyHeader>
                <EmptyMedia variant="icon"><DatabaseIcon /></EmptyMedia>
                <EmptyTitle>没有可列出的业务记录</EmptyTitle>
                <EmptyDescription>{data.note}</EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
          {!isSchema && data && data.total > 0 && data.rows.length === 0 && (
            <p className="rounded-lg border px-4 py-6 text-sm text-muted-foreground">
              没有匹配「{data.query}」的记录
            </p>
          )}
          {!isSchema && data && data.rows.length > 0 && (
            <div className="catalog-scroll min-h-0 flex-1 rounded-lg border">
              <table className="w-max min-w-full border-separate border-spacing-0 text-left text-xs">
                <thead>
                  <tr className="text-muted-foreground">
                    {data.columns.map((col) => (
                      <th key={col.key} scope="col" className="sticky top-0 z-10 border-b border-r bg-muted px-3 py-2.5 font-medium whitespace-nowrap last:border-r-0">
                        {col.label}
                      </th>
                    ))}
                    {showActions && (
                      <th
                        scope="col"
                        // w-px 让列宽按内容收缩（按钮组多宽列就多宽），避免固定宽度把「删除」裁掉、表头与按钮组错位
                        className="sticky top-0 right-0 z-20 w-px border-b border-l border-border/80 bg-muted px-3 py-2.5 text-center font-medium whitespace-nowrap shadow-[-6px_0_12px_-8px_rgb(15_23_42/0.18)]"
                      >
                        操作
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row, index) => {
                    const id = typeof row.id === 'number' ? row.id : Number(row.id)
                    const busy = deletingId === id
                    const status = String(row.status ?? 'pending')
                    const applicationId = row.applicationId == null ? '' : String(row.applicationId)
                    const reviewReason = typeof row.reviewReason === 'string' ? row.reviewReason : ''
                    const reviewedAt = typeof row.reviewedAt === 'string' ? row.reviewedAt : ''
                    const canReviewRow = reviewable && Number.isFinite(id) && status === 'pending_review'
                    const reviewTitle = !reviewable
                      ? undefined
                      : status !== 'pending_review'
                        ? '只有待审核（已生成尽调报告）的申请可以审核'
                        : `审核 ${applicationId}`
                    return (
                      <tr key={Number.isFinite(id) ? id : index} className="group/row">
                        {data.columns.map((col) => {
                          const text = cellText(col.key, row[col.key] ?? null)
                          const reviewTip = col.key === 'status' && reviewReason
                            ? `审核原因：${reviewReason}${reviewedAt ? `（${reviewedAt}）` : ''}`
                            : undefined
                          return (
                            <td
                              key={col.key}
                              className="border-b border-r border-border/60 bg-card/60 px-3 py-2.5 whitespace-nowrap last:border-r-0 group-hover/row:bg-muted/35"
                              title={reviewTip ?? (text.length > 32 ? text : undefined)}
                            >
                              {text}
                            </td>
                          )
                        })}
                        {showActions && (
                          <td className="sticky right-0 z-10 w-px border-b border-l border-border/80 bg-card/95 px-2.5 py-1.5 text-center whitespace-nowrap shadow-[-6px_0_12px_-8px_rgb(15_23_42/0.14)] group-hover/row:bg-muted/50">
                            <div
                              role="group"
                              aria-label="行操作"
                              className="inline-flex items-center overflow-hidden rounded-lg border border-border/70 bg-background/80 p-0.5 shadow-sm"
                            >
                              {reviewable && (
                                <>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="xs"
                                    className="h-7 cursor-pointer gap-1 rounded-md px-1.5 text-brand hover:bg-brand-soft hover:text-brand"
                                    disabled={!canReviewRow || busy}
                                    title={reviewTitle}
                                    onClick={() => setReviewTarget({ id, applicationId, status })}
                                  >
                                    <ClipboardCheckIcon className="size-3.5" />
                                    审核
                                  </Button>
                                  {writable && <span aria-hidden className="mx-0.5 h-4 w-px shrink-0 bg-border/80" />}
                                </>
                              )}
                              {writable && (
                                <>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="xs"
                                    className="h-7 cursor-pointer gap-1 rounded-md px-1.5 text-tech hover:bg-tech-soft hover:text-tech"
                                    disabled={!Number.isFinite(id) || busy}
                                    onClick={() => setForm({ mode: 'edit', row })}
                                  >
                                    <PencilIcon className="size-3.5" />
                                    编辑
                                  </Button>
                                  <span aria-hidden className="mx-0.5 h-4 w-px shrink-0 bg-border/80" />
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="xs"
                                    className="h-7 cursor-pointer gap-1 rounded-md px-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive"
                                    disabled={!Number.isFinite(id) || busy}
                                    onClick={() => void removeRow(id)}
                                  >
                                    {busy ? <Spinner className="size-3.5" /> : <Trash2Icon className="size-3.5" />}
                                    删除
                                  </Button>
                                </>
                              )}
                            </div>
                          </td>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {writable && !isSchema && form && (
        <RecordFormDialog
          key={`${form.mode}:${String(form.row?.id ?? 'new')}`}
          actorId={actorId}
          kind={kind as WritableKind}
          mode={form.mode}
          initial={form.row}
          open
          onClose={() => setForm(null)}
          onSaved={refresh}
        />
      )}

      {reviewable && reviewTarget && (
        <ReviewDialog
          key={`review:${reviewTarget.id}`}
          actorId={actorId}
          target={reviewTarget}
          open
          onClose={() => setReviewTarget(null)}
          onReviewed={refresh}
        />
      )}
    </div>
  )
}
