/**
 * 尽调报告：报告的检索与查看（评审维度②「会议与资产管理」）。
 * 报告本身没有状态：不做确认 / 驳回 / 归档，审核结论记在贷款申请上。
 * 列表与详情各自滚动：左侧检索与表头固定，右侧报告详情独立滚动。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ActivityIcon, FileTextIcon, SearchIcon, XIcon } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'

import { AssetDetailTabs } from '@/components/workspace/asset-detail-tabs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { api } from '@/lib/api'
import type { WorkspaceAsset, WorkspaceAssetDetail, WorkspaceAssetList } from '@/lib/types'
import { cn } from '@/lib/utils'

function ReportListLoading() {
  const reduce = useReducedMotion()
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="正在加载尽调报告"
      className="relative flex flex-col items-center justify-center gap-4 overflow-hidden rounded-xl border border-brand/15 bg-gradient-to-br from-brand-soft/50 via-card to-tech-soft/30 px-6 py-14"
    >
      {!reduce && (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/40 to-transparent"
          animate={{ left: ['-35%', '120%'] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
      <motion.div
        className="relative flex size-12 items-center justify-center rounded-2xl border border-brand/25 bg-card/90 shadow-sm"
        animate={reduce ? undefined : { scale: [1, 1.04, 1] }}
        transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
      >
        <Spinner className="size-6 text-brand" />
      </motion.div>
      <p className="relative flex items-center gap-0.5 text-sm font-medium text-foreground/80">
        <span>正在加载尽调报告</span>
        <span className="inline-flex w-6 justify-start" aria-hidden>
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="inline-block"
              animate={reduce ? undefined : { opacity: [0.25, 1, 0.25] }}
              transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut', delay: i * 0.2 }}
            >
              .
            </motion.span>
          ))}
        </span>
      </p>
      <div className="relative flex gap-1.5" aria-hidden>
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="size-1.5 rounded-full bg-brand/70"
            animate={reduce ? undefined : { y: [0, -5, 0], opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 0.75, repeat: Infinity, ease: 'easeInOut', delay: i * 0.12 }}
          />
        ))}
      </div>
    </div>
  )
}

function reportTitle(asset: WorkspaceAsset): string {
  const generatedAt = new Date(asset.reportGeneratedAt)
  const date = Number.isNaN(generatedAt.getTime())
    ? '日期未记录'
    : `${generatedAt.getFullYear()}${String(generatedAt.getMonth() + 1).padStart(2, '0')}${String(generatedAt.getDate()).padStart(2, '0')}`
  return `${asset.enterpriseName || '企业名称未登记'}_${asset.applicationId || '申请未关联'}_${date}`
}

function reportTraceTitle(asset: WorkspaceAsset): string {
  const company = asset.enterpriseName || '企业名称未登记'
  const amount = asset.applyAmount == null
    ? '金额未记录'
    : `${asset.applyAmount.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}万元`
  return `${company}贷款${amount}信贷尽调报告轨迹`
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

export function WorkspacePage({ actorId, applicationId = '', onClearApplication }: {
  actorId: string
  /** 从「智能尽调」的查看报告跳转带入：只列出该贷款编号对应的尽调报告 */
  applicationId?: string
  onClearApplication?: () => void
}) {
  const [page, setPage] = useState<WorkspaceAssetList | null>(null)
  const [keyword, setKeyword] = useState('')
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [traceSelectionVersion, setTraceSelectionVersion] = useState(0)
  const traceRef = useRef<HTMLDivElement>(null)
  const [detail, setDetail] = useState<WorkspaceAssetDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const detailRef = useRef<HTMLDivElement | null>(null)

  const load = useCallback(async () => {
    if (!actorId) return
    setLoading(true)
    setError(null)
    // 清掉旧列表：清除申请编号 / 检索重查时也要露出加载态，不能继续展示上一份结果
    setPage(null)
    setDetail(null)
    try {
      // applicationId 走服务端过滤：从智能尽调跳过来时只查这笔审批的报告
      const data = await api.assets(actorId, {
        keyword: query,
        applicationId: applicationId || undefined,
        limit: 50,
      })
      setPage(data)
      setSelectedId((current) => (
        current && data.assets.some((item) => item.id === current)
          ? current
          : data.assets[0]?.id ?? null))
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : '尽调报告加载失败')
    } finally {
      setLoading(false)
    }
  }, [actorId, query, applicationId])

  // @why 数据请求放在 effect 里由外部系统驱动；用 0ms 定时器把 setState 移出 effect 同步阶段
  useEffect(() => {
    const timer = window.setTimeout(() => { void load() }, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  useEffect(() => {
    let active = true
    if (!selectedId) return () => { active = false }
    api.asset(actorId, selectedId)
      .then((item) => { if (active) setDetail(item) })
      .catch((exc: unknown) => { if (active) setError(exc instanceof Error ? exc.message : '报告详情加载失败') })
    return () => { active = false }
  }, [actorId, selectedId])

  // @why 右侧详情独立滚动，切换报告时回到顶部，避免停留在上一份报告的滚动位置
  useEffect(() => {
    detailRef.current?.scrollTo({ top: 0 })
  }, [selectedId])

  const current = selectedId && detail?.id === selectedId ? detail : null
  const assets = page?.assets ?? []

  return (
    <div className="grid grid-cols-1 gap-4 xl:min-h-0 xl:flex-1 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Card className="flex min-h-[420px] flex-col xl:min-h-0">
        <CardHeader className="shrink-0 border-b border-border/70 bg-tech-soft/35">
          <CardTitle className="flex items-center gap-2 tracking-tight">
            <FileTextIcon className="size-4" /> 尽调报告
            {page ? <span className="text-xs font-normal text-muted-foreground">共 {page.total} 份</span> : null}
          </CardTitle>
          <CardDescription>
            {applicationId
              ? `当前只显示贷款编号 ${applicationId} 对应的尽调报告；清除过滤可查看全部报告。`
              : '每份尽调报告生成后自动进入列表，可查看报告与相关证据，并按企业 / 申请编号 / 关键词检索。'}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <div className="relative min-w-56 flex-1">
              <SearchIcon className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground" />
              <Input
                value={keyword}
                className="pl-8"
                placeholder={applicationId ? '在当前申请下按企业名称 / 报告标题检索' : '按企业名称 / 申请编号 / 报告标题检索'}
                aria-label="检索尽调报告"
                onChange={(event) => setKeyword(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') setQuery(keyword) }}
              />
            </div>
            <Button type="button" size="sm" variant="outline" onClick={() => setQuery(keyword)}>
              <SearchIcon /> 检索
            </Button>
            {applicationId && (
              <span className="inline-flex items-center gap-1 rounded-full border border-brand/40 bg-brand-soft px-2.5 py-1 text-xs text-brand">
                申请编号：{applicationId}
                {onClearApplication && (
                  <button
                    type="button"
                    aria-label="清除申请编号过滤"
                    title="查看全部尽调报告"
                    className="cursor-pointer rounded-full p-0.5 hover:bg-brand/10"
                    onClick={onClearApplication}
                  >
                    <XIcon className="size-3" />
                  </button>
                )}
              </span>
            )}
          </div>

          {error ? (
            <p role="alert" className="shrink-0 rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800">
              {error}
            </p>
          ) : null}

          {loading ? (
            <ReportListLoading />
          ) : assets.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon"><FileTextIcon /></EmptyMedia>
                <EmptyTitle>
                  {applicationId ? `贷款编号 ${applicationId} 还没有尽调报告` : '还没有尽调报告'}
                </EmptyTitle>
                <EmptyDescription>
                  {applicationId
                    ? '这笔申请尚未生成尽调报告（待处理）。先在「智能尽调」对这笔申请发起尽调，报告生成后即可在这里查看。'
                    : '在「智能尽调」完成一次企业尽调后，报告会自动进入这个列表；失败与澄清不生成报告。'}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <div className="min-h-0 flex-1 overflow-auto">
              <table className="w-full text-sm">
                {/* @why 表头粘在列表滚动容器顶部：sticky 要落在 th 上，且外层不能再套一个 overflow 容器 */}
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="sticky top-0 z-10 bg-card px-2 py-2 font-medium">报告名称</th>
                    <th className="sticky top-0 z-10 bg-card px-2 py-2 font-medium">申请编号</th>
                    <th className="sticky top-0 z-10 bg-card px-2 py-2 font-medium">贷款金额（万元）</th>
                    <th className="sticky top-0 z-10 bg-card px-2 py-2 font-medium">报告生成时间</th>
                    <th className="sticky top-0 z-10 bg-card px-2 py-2 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.map((asset) => (
                    <tr
                      key={asset.id}
                      className={cn(
                        'border-b border-border/60 transition-colors hover:bg-muted/60',
                        selectedId === asset.id && 'bg-brand/5',
                      )}
                    >
                      <td className="max-w-72 px-2 py-2">
                        <a
                          className="block truncate font-medium text-brand underline-offset-2 hover:underline"
                          title={reportTitle(asset)}
                          href={`/report-preview.html?runId=${encodeURIComponent(asset.runId)}`}
                          target="_blank"
                          rel="noreferrer"
                        >{reportTitle(asset)}</a>
                      </td>
                      <td className="px-2 py-2 text-xs">{asset.applicationId ?? '未关联'}</td>
                      <td className="px-2 py-2 font-mono text-xs">{asset.applyAmount == null ? '—' : asset.applyAmount.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}</td>
                      <td className="px-2 py-2 font-mono text-xs text-muted-foreground">{formatTime(asset.reportGeneratedAt)}</td>
                      <td className="px-2 py-2">
                        <Button size="sm" variant="outline" aria-controls="asset-report-trace" onClick={() => {
                          setSelectedId(asset.id)
                          setTraceSelectionVersion(value => value + 1)
                          traceRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
                        }}><ActivityIcon />报告轨迹</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card id="asset-report-trace" ref={traceRef} className="flex min-h-[420px] flex-col xl:min-h-0">
        <CardHeader className="shrink-0 border-b border-border/70 bg-tech-soft/35">
          <CardTitle className="break-words tracking-tight">{current ? reportTraceTitle(current) : '报告轨迹'}</CardTitle>
          <CardDescription>查看报告生成过程与当次证据快照。</CardDescription>
        </CardHeader>
        <CardContent ref={detailRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
          {!current ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              {selectedId ? '正在加载报告…' : '选择左侧报告查看轨迹'}
            </p>
          ) : (
            <AssetDetailTabs key={`${actorId}:${current.id}:${current.runId}`} actorId={actorId} runId={current.runId} traceSelectionVersion={traceSelectionVersion} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export type { WorkspaceAsset }
