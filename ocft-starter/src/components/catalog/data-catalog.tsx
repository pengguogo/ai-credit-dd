/**
 * 左侧业务目录：按贷款申请选择尽调对象；筛选走 GET /api/agent/catalog。
 * 只做选择与查看：审核在「贷款管理-贷款申请」里做，这里不再提供审核操作。
 */
import { DatabaseIcon, FileTextIcon, FilterXIcon, PanelLeftCloseIcon, SearchIcon, XIcon } from 'lucide-react'
import { Fragment, useEffect, useState, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { applicationQuestion } from '@/data/scenario'
import { ApiError, api } from '@/lib/api'
import type { CatalogKind } from '@/lib/catalog-tables'
import { applyEnterpriseToQuestion } from '@/lib/enterprise-input'
import type { Catalog } from '@/lib/types'
import { cn } from '@/lib/utils'

const STATUS_LABEL: Record<string, string> = {
  pending: '待处理',
  pending_review: '待审核',
  approved: '审核通过',
  rejected: '审核不通过',
}

function cellText(key: string, value: string | number | null): string {
  if (value == null || value === '') return '—'
  if (key === 'status') return STATUS_LABEL[String(value)] ?? String(value)
  if (typeof value === 'number') return value.toLocaleString('zh-CN')
  return String(value)
}

function emptyFilterTitle(data: Catalog): string {
  if (data.query) return '暂无匹配记录'
  if (data.approvalStatus === 'open') return '暂无待处理或待审核的申请'
  if (data.approvalStatus) return `暂无${STATUS_LABEL[data.approvalStatus] ?? data.approvalStatus}申请`
  return '暂无匹配记录'
}

function emptyFilterDescription(data: Catalog): string {
  const recordType = data.kind === 'applications' ? '审批记录' : '业务记录'
  if (data.query && data.approvalStatus) return `“${data.query}”与当前状态筛选下没有可展示的审批记录`
  if (data.query) return `没有找到与“${data.query}”匹配的${recordType}`
  return `当前筛选条件下没有可展示的${recordType}`
}

function filterPlaceholder(kind: CatalogKind): string {
  if (kind === 'enterprises') return '按企业编号、名称、行业筛选'
  // 状态也可用关键字搜（待处理/待审核/审核通过/审核不通过）；上方芯片是按状态过滤，两者勿混
  if (kind === 'applications') {
    return '编号 / 企业 / 用途'
  }
  return '按企业编号或关键字筛选'
}

function HintButton({ tip, selected, onClick, children }: {
  tip: string
  selected: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        type="button"
        className={`cursor-pointer rounded px-1 py-0.5 font-medium underline-offset-2 hover:bg-brand-soft hover:underline ${
          selected ? 'bg-brand-soft text-brand' : 'text-brand'
        }`}
        onClick={onClick}
      >
        {children}
      </TooltipTrigger>
      <TooltipContent side="right" className="max-w-72 text-left leading-relaxed">
        {tip}
      </TooltipContent>
    </Tooltip>
  )
}

function CatalogTable({ data, kind, chatInput, emptyEnterpriseExample, selectedEnterpriseId, selectedApplicationId, onSelectEnterprise, onSelectApplication, onViewReport }: {
  data: Catalog
  kind: CatalogKind
  chatInput: string
  emptyEnterpriseExample: string
  selectedEnterpriseId?: string | null
  selectedApplicationId?: string | null
  onSelectEnterprise?: (enterpriseId: string) => void
  onSelectApplication?: (applicationId: string) => void
  /** 有报告且当前角色可看报告时才会传入；缺省时「查看报告」置灰 */
  onViewReport?: (applicationId: string) => void
}) {
  const showReport = kind === 'applications'
  const colSpan = data.columns.length + (showReport ? 1 : 0)
  return (
    <div className="catalog-scroll approval-scroll min-h-0 min-w-0 flex-1 rounded-lg border bg-card">
      <table className="h-full w-max min-w-full border-separate border-spacing-0 text-left text-xs">
        <thead>
          <tr className="text-muted-foreground">
            {data.columns.map((col) => (
              <Fragment key={col.key}>
                <th scope="col" className="sticky top-0 z-10 border-b border-r bg-muted px-3 py-2.5 font-medium whitespace-nowrap last:border-r-0">{col.label}</th>
                {showReport && col.key === 'status' && (
                  <th scope="col" className="sticky top-0 z-10 border-b border-r bg-muted px-3 py-2.5 font-medium whitespace-nowrap last:border-r-0">查看报告</th>
                )}
              </Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, index) => {
            const enterpriseId = row.enterpriseId != null && row.enterpriseId !== ''
              ? String(row.enterpriseId)
              : ''
            const applicationId = row.applicationId != null && row.applicationId !== ''
              ? String(row.applicationId)
              : ''
            const status = String(row.status ?? 'pending')
            // 后端按是否已建档尽调报告给出 hasReport，前端不靠状态猜
            const hasReport = Boolean(row['hasReport'])
            const reviewReason = typeof row.reviewReason === 'string' ? row.reviewReason : ''
            const selected = kind === 'enterprises'
              ? Boolean(enterpriseId && selectedEnterpriseId === enterpriseId)
              : kind === 'applications'
                ? Boolean(applicationId && selectedApplicationId === applicationId)
                : false
            return (
              <tr key={index} className={selected ? 'bg-brand-soft/40' : undefined}>
                {data.columns.map((col) => {
                  const text = cellText(col.key, row[col.key] ?? null)
                  const clickEnterprise = col.key === 'enterpriseId'
                    && enterpriseId
                    && onSelectEnterprise
                  const clickApplication = kind === 'applications'
                    && col.key === 'applicationId'
                    && applicationId
                    && onSelectApplication
                  return (
                    <Fragment key={col.key}>
                      <td
                        key={col.key}
                        className={`border-b border-r px-3 py-2.5 whitespace-nowrap last:border-r-0 ${selected ? 'bg-transparent' : 'bg-card'}`}
                        title={typeof text === 'string' && text.length > 24 ? text : undefined}
                      >
                        {clickEnterprise ? (
                          <HintButton
                            tip={applyEnterpriseToQuestion(chatInput, enterpriseId, emptyEnterpriseExample)}
                            selected={selectedEnterpriseId === enterpriseId}
                            onClick={() => onSelectEnterprise(enterpriseId)}
                          >
                            {text}
                          </HintButton>
                        ) : clickApplication ? (
                          <HintButton
                            tip={applicationQuestion(applicationId)}
                            selected={selectedApplicationId === applicationId}
                            onClick={() => onSelectApplication(applicationId)}
                          >
                            {text}
                          </HintButton>
                        ) : col.key === 'status' ? (
                          <span
                            title={reviewReason ? `审核原因：${reviewReason}` : undefined}
                            className={cn(
                              status === 'pending' && 'text-muted-foreground',
                              status === 'pending_review' && 'text-brand',
                              status === 'approved' && 'text-success',
                              status === 'rejected' && 'text-destructive',
                            )}
                          >{text}</span>
                        ) : text}
                      </td>
                      {showReport && col.key === 'status' && (
                        <td className={`border-b border-r px-2 py-1.5 whitespace-nowrap last:border-r-0 ${selected ? 'bg-transparent' : 'bg-card'}`}>
                          <Button
                            type="button"
                            size="xs"
                            variant="outline"
                            disabled={!hasReport || !onViewReport || !applicationId}
                            title={!hasReport
                              ? '该申请尚未生成尽调报告（待处理）'
                              : !onViewReport
                                ? '当前角色没有报告查看权限'
                                : `查看 ${applicationId} 的尽调报告`}
                            onClick={() => onViewReport?.(applicationId)}
                          >
                            <FileTextIcon /> 查看报告
                          </Button>
                        </td>
                      )}
                    </Fragment>
                  )
                })}
              </tr>
            )
          })}
          <tr aria-hidden className="h-full">
            {Array.from({ length: colSpan }, (_, i) => (
              <td key={i} className="border-r p-0 last:border-r-0" />
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function CatalogPane({ actorId, scenarioId, kind, reloadKey, chatInput, emptyEnterpriseExample, selectedEnterpriseId, selectedApplicationId, onSelectEnterprise, onSelectApplication, onViewReport }: {
  actorId: string
  scenarioId: string
  kind: CatalogKind
  /** 导入成功后自增，触发重新读取 */
  reloadKey: number
  chatInput: string
  emptyEnterpriseExample: string
  selectedEnterpriseId?: string | null
  selectedApplicationId?: string | null
  onSelectEnterprise?: (enterpriseId: string) => void
  onSelectApplication?: (applicationId: string) => void
  onViewReport?: (applicationId: string) => void
}) {
  const [data, setData] = useState<Catalog | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState('')
  const [keyword, setKeyword] = useState('')

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
    // 智能尽调的申请列表只列未审结的（待处理 / 待审核）；已审核通过 / 不通过的不再出现
    api.catalog(actorId, scenarioId, keyword, kind, kind === 'applications' ? 'open' : '')
      .then((body) => {
        if (cancelled) return
        setData(body)
        setError('')
      })
      .catch((exc: unknown) => {
        if (cancelled) return
        setError(exc instanceof ApiError ? exc.message : '业务表加载失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [actorId, scenarioId, keyword, kind, reloadKey])

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

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="space-y-1.5">
        <label htmlFor={`catalog-filter-${kind}`} className="sr-only">筛选业务记录</label>
        <div className="flex items-center overflow-hidden rounded-lg border border-input bg-card shadow-sm focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
          <Input
            id={`catalog-filter-${kind}`}
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
            placeholder={filterPlaceholder(kind)}
            className="h-9 rounded-none border-0 bg-transparent text-xs shadow-none focus-visible:ring-0"
          />
          {draft && (
            <Button
              type="button"
              variant="ghost"
              className="h-9 rounded-none px-2 text-muted-foreground hover:text-foreground"
              aria-label="清空"
              onClick={clearFilter}
            >
              <XIcon />
            </Button>
          )}
          <Button
            type="button"
            variant="ghost"
            className="h-9 rounded-none border-l px-3 text-muted-foreground hover:text-foreground"
            aria-label="搜索"
            onClick={searchNow}
          >
            {loading ? <Spinner /> : <SearchIcon />}
          </Button>
        </div>
      </div>

      {loading && !data && (
        <p className="flex items-center gap-2 px-1 py-3 text-sm text-muted-foreground">
          <Spinner /> 读取业务表…
        </p>
      )}
      {!loading && error && !data && (
        <p role="alert" className="px-1 py-3 text-sm text-destructive">{error}</p>
      )}
      {data && data.total === 0 && (
        <Empty className="h-full border border-dashed">
          <EmptyHeader>
            <EmptyMedia variant="icon"><DatabaseIcon /></EmptyMedia>
            <EmptyTitle>没有可列出的业务记录</EmptyTitle>
            <EmptyDescription>{data.note}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
      {data && data.total > 0 && data.rows.length === 0 && (
        <Empty className="h-full border border-dashed bg-muted/10">
          <EmptyHeader>
            <EmptyMedia variant="icon" className="bg-brand-soft text-brand"><FilterXIcon /></EmptyMedia>
            <EmptyTitle>{emptyFilterTitle(data)}</EmptyTitle>
            <EmptyDescription>{emptyFilterDescription(data)}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
      {data && data.rows.length > 0 && (
        <CatalogTable
          data={data}
          kind={kind}
          chatInput={chatInput}
          emptyEnterpriseExample={emptyEnterpriseExample}
          selectedEnterpriseId={selectedEnterpriseId}
          selectedApplicationId={selectedApplicationId}
          onSelectEnterprise={onSelectEnterprise}
          onSelectApplication={onSelectApplication}
          onViewReport={onViewReport}
        />
      )}
    </div>
  )
}

export function DataCatalog({
  onCollapse,
  actorId,
  scenarioId,
  chatInput,
  emptyEnterpriseExample,
  onSelectEnterprise,
  onSelectApplication,
  selectedEnterpriseId,
  selectedApplicationId,
  showApplications = true,
  onViewReport,
}: {
  actorId: string
  scenarioId: string
  onCollapse: () => void
  chatInput: string
  emptyEnterpriseExample: string
  onSelectEnterprise?: (enterpriseId: string) => void
  onSelectApplication?: (applicationId: string) => void
  selectedEnterpriseId?: string | null
  selectedApplicationId?: string | null
  showApplications?: boolean
  /** 点「查看报告」：跳到贷款管理-尽调报告并按该申请筛选 */
  onViewReport?: (applicationId: string) => void
}) {
  return (
    <Card className="h-full gap-2 pt-0">
      <CardHeader className="flex flex-row items-center justify-between border-b border-border/70 bg-tech-soft/35 py-1.5 [.border-b]:pb-1.5">
        <CardTitle className="tracking-tight">业务数据</CardTitle>
        <CardAction>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="收起业务数据"
            title="收起业务数据"
            onClick={onCollapse}
          >
            <PanelLeftCloseIcon />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col overflow-hidden p-3">
        {showApplications ? (
          <CatalogPane
            actorId={actorId}
            scenarioId={scenarioId}
            kind="applications"
            reloadKey={0}
            chatInput={chatInput}
            emptyEnterpriseExample={emptyEnterpriseExample}
            selectedEnterpriseId={selectedEnterpriseId}
            selectedApplicationId={selectedApplicationId}
            onSelectEnterprise={onSelectEnterprise}
            onSelectApplication={onSelectApplication}
            onViewReport={onViewReport}
          />
        ) : (
          <p className="text-sm text-muted-foreground">当前账号没有审批表查看权限，请联系管理员授权后选择贷款申请。</p>
        )}
      </CardContent>
    </Card>
  )
}
