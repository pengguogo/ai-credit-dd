/** 单维度核对：选择贷款申请，关联企业事实，各步骤始终绑定同一申请。 */
import { ChevronsUpDownIcon, SearchIcon, SparklesIcon } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useId, useMemo, useRef, useState } from 'react'

import { DependencyPanel } from '@/components/report/dependency-panel'
import { THEME_CLASS } from '@/components/report/dim-theme'
import { DimGlyph, DimStepRail, Rise } from '@/components/report/dim-visuals'
import { StepResultView } from '@/components/report/step-result'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { SCENARIO_ID } from '@/data/scenario'
import { ApiError, api } from '@/lib/api'
import { readReportContext, REPORT_DIMS, reportPath, type ReportDim } from '@/lib/report-dims'
import type { DdStepResult } from '@/lib/types'
import { cn } from '@/lib/utils'

type ApplicationOption = {
  applicationId: string
  enterpriseId: string
  enterpriseName: string
  applyAmount: string
  loanPurpose: string
  loanTermMonths: string
}

function cell(row: Record<string, string | number | null>, key: string): string {
  const value = row[key]
  return value == null || value === '' ? '' : String(value)
}

function applicationLabel(item: ApplicationOption): string {
  return `${item.applicationId} · ${item.enterpriseName || item.enterpriseId}`
}

export function DimensionPage({ actorId, dim, onNavigate }: {
  actorId: string
  dim: ReportDim
  onNavigate: (href: string) => void
}) {
  const listId = useId()
  const reduce = useReducedMotion()
  const initial = readReportContext()
  const [applicationId, setApplicationId] = useState(initial.applicationId)
  const [options, setOptions] = useState<ApplicationOption[]>([])
  const [optionsError, setOptionsError] = useState('')
  const [filter, setFilter] = useState('')
  const [open, setOpen] = useState(false)
  const [result, setResult] = useState<DdStepResult | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(Boolean(initial.applicationId))
  const [loadingOptions, setLoadingOptions] = useState(true)
  const rootRef = useRef<HTMLDivElement>(null)
  const requestRef = useRef(0)
  const [refresh, setRefresh] = useState(0)
  const theme = THEME_CLASS[dim.theme]

  const selected = options.find((item) => item.applicationId === applicationId) ?? null
  const enterpriseId = selected?.enterpriseId ?? result?.enterpriseId ?? ''
  const selectedLabel = selected ? applicationLabel(selected) : ''
  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q || (selectedLabel && q === selectedLabel.toLowerCase())) return options
    return options.filter((item) =>
      [item.applicationId, item.enterpriseId, item.enterpriseName, item.loanPurpose,
        applicationLabel(item)].some((value) => value.toLowerCase().includes(q)))
  }, [filter, options, selectedLabel])

  useEffect(() => {
    let cancelled = false
    setLoadingOptions(true)
    api.catalog(actorId, SCENARIO_ID, '', 'applications')
      .then((body) => {
        if (cancelled) return
        setOptions(body.rows.map((row) => ({
          applicationId: cell(row, 'applicationId'),
          enterpriseId: cell(row, 'enterpriseId'),
          enterpriseName: cell(row, 'enterpriseName'),
          applyAmount: cell(row, 'applyAmount'),
          loanPurpose: cell(row, 'loanPurpose'),
          loanTermMonths: cell(row, 'loanTermMonths'),
        })).filter((row) => row.applicationId))
        setOptionsError('')
      })
      .catch((exc: unknown) => {
        if (cancelled) return
        setOptions([])
        setOptionsError(exc instanceof ApiError ? exc.message : '贷款申请列表加载失败')
      })
      .finally(() => {
        if (!cancelled) setLoadingOptions(false)
      })
    return () => { cancelled = true }
  }, [actorId])

  useEffect(() => {
    const onDoc = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const runAnalyze = (application: string) => {
    requestRef.current += 1
    const aid = application.trim()
    if (!aid) {
      setError('请选择贷款申请')
      setResult(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setResult(null)
    setError('')
    onNavigate(reportPath(dim.slug, { applicationId: aid }))
    setRefresh((value) => value + 1)
  }

  const pickApplication = (item: ApplicationOption) => {
    setApplicationId(item.applicationId)
    setFilter(applicationLabel(item))
    setOpen(false)
    runAnalyze(item.applicationId)
  }

  useEffect(() => {
    setApplicationId(initial.applicationId)
    setOpen(false)
    const hit = options.find((item) => item.applicationId === initial.applicationId)
    setFilter(hit ? applicationLabel(hit) : initial.applicationId)
  }, [initial.applicationId, options])

  // 所有步骤绑定所选申请；取消标记和序号阻止旧请求覆盖新对象。
  useEffect(() => {
    const request = ++requestRef.current
    setResult(null)
    setError('')
    setLoading(Boolean(initial.applicationId))
    if (!initial.applicationId) return
    let cancelled = false
    api.ddStep(actorId, { step: dim.slug, applicationId: initial.applicationId })
      .then((body) => {
        if (cancelled || request !== requestRef.current) return
        setResult(body)
        setError('')
      })
      .catch((exc: unknown) => {
        if (cancelled || request !== requestRef.current) return
        setResult(null)
        setError(exc instanceof ApiError ? exc.message : '本步分析失败')
      })
      .finally(() => {
        if (!cancelled && request === requestRef.current) setLoading(false)
      })
    return () => { cancelled = true }
  }, [actorId, dim.slug, initial.applicationId, refresh])

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 pb-6">
      <Rise>
        <header className="relative overflow-hidden rounded-2xl border border-border/70 bg-card/75 shadow-[inset_0_1px_0_rgb(255_255_255/0.55)]">
          <div
            aria-hidden
            className={cn(
              'pointer-events-none absolute inset-0 bg-gradient-to-br opacity-90',
              theme.glow,
            )}
          />
          {!reduce && (
            <motion.div
              aria-hidden
              className="pointer-events-none absolute -right-8 -top-10 size-48 rounded-full bg-brand/15 blur-3xl"
              animate={{ opacity: [0.35, 0.7, 0.35], scale: [0.95, 1.08, 0.95] }}
              transition={{ duration: 5.5, repeat: Infinity, ease: 'easeInOut' }}
            />
          )}
          <div className="relative space-y-4 px-5 py-5 sm:px-7 sm:py-6">
            <DimStepRail
              dims={REPORT_DIMS}
              active={dim.slug}
              onSelect={(slug) => onNavigate(reportPath(slug, { applicationId }))}
            />
            <div className="flex flex-wrap items-start gap-4">
              <motion.div
                key={dim.slug}
                className={cn(
                  'flex size-14 shrink-0 items-center justify-center rounded-2xl border shadow-sm',
                  theme.chip,
                )}
                initial={reduce ? false : { rotate: -8, scale: 0.88, opacity: 0 }}
                animate={{ rotate: 0, scale: 1, opacity: 1 }}
                transition={{ type: 'spring', stiffness: 260, damping: 18 }}
              >
                <DimGlyph slug={dim.slug} className="size-7" />
              </motion.div>
              <div className="min-w-0 flex-1">
                <p className="font-mono text-[11px] font-medium tracking-[0.14em] text-brand uppercase">
                  Step {String(dim.step).padStart(2, '0')} / {String(REPORT_DIMS.length).padStart(2, '0')}
                  {dim.slug === 'report' ? ' · 报告导出' : ' · 单角色'}
                </p>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
                  {dim.label}
                </h1>
                <p className="mt-2 max-w-2xl text-sm leading-relaxed text-foreground/80">
                  {dim.hero}
                </p>
                <p className="mt-2 max-w-2xl text-xs text-muted-foreground">{dim.blurb}</p>
                <p className="mt-2 inline-flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
                  <SparklesIcon className="size-3 text-brand" aria-hidden />
                  涉及 tool：{dim.tools.join(' · ')}
                </p>
              </div>
            </div>
          </div>
        </header>
      </Rise>

      <Rise delay={0.06}>
        <form
          className={cn(
            // 展开下拉时不要 overflow-hidden，否则 absolute 列表会被裁切；并抬高层级盖住下方依赖/结果区
            'surface-panel relative rounded-2xl px-5 py-4',
            open ? 'z-40 overflow-visible' : 'overflow-hidden',
          )}
          onSubmit={(e) => {
            e.preventDefault()
            runAnalyze(applicationId)
          }}
        >
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-sm font-medium">分析对象</p>
              <p className="mt-1 text-xs text-muted-foreground">
                选择审批表中的贷款申请，以关联企业为调查主体；切换步骤保留同一笔申请。
              </p>
            </div>
            {loading && (
              <motion.span
                className="inline-flex items-center gap-1.5 rounded-full border border-brand/30 bg-brand-soft px-2.5 py-1 text-[11px] font-medium text-brand"
                animate={reduce ? undefined : { opacity: [0.7, 1, 0.7] }}
                transition={{ duration: 1.4, repeat: Infinity }}
              >
                <Spinner className="size-3" /> Agent 取证中
              </motion.span>
            )}
          </div>
          <div className="mt-3">
            <div className="flex flex-wrap items-end gap-3">
              <div ref={rootRef} className="relative min-w-[16rem] flex-1">
                <label htmlFor={listId} className="text-xs text-muted-foreground">贷款申请</label>
                <div className="relative mt-1">
                  <Input
                    id={listId}
                    role="combobox"
                    aria-expanded={open}
                    aria-controls={`${listId}-list`}
                    aria-autocomplete="list"
                    value={filter}
                    disabled={loadingOptions}
                    placeholder={loadingOptions ? '加载贷款申请列表…' : '搜索贷款编号、企业或用途'}
                    className="h-10 pr-9 font-mono text-sm"
                    autoComplete="off"
                    onFocus={() => setOpen(true)}
                    onChange={(e) => {
                      setFilter(e.target.value)
                      setOpen(true)
                      const exact = options.find((item) =>
                        item.applicationId === e.target.value.trim()
                        || applicationLabel(item) === e.target.value.trim())
                      setApplicationId(exact?.applicationId ?? '')
                      requestRef.current += 1
                      setResult(null)
                      setLoading(false)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Escape') setOpen(false)
                      if (e.key === 'ArrowDown') setOpen(true)
                    }}
                  />
                  <button
                    type="button"
                    className="absolute inset-y-0 right-0 z-[1] flex w-9 cursor-pointer items-center justify-center text-muted-foreground"
                    aria-label="展开贷款申请列表"
                    onClick={() => setOpen((v) => !v)}
                  >
                    <ChevronsUpDownIcon className="size-4" />
                  </button>
                  {open && (
                    <ul
                      id={`${listId}-list`}
                      role="listbox"
                      className="surface-panel-solid absolute inset-x-0 top-full z-50 mt-1 max-h-64 overflow-auto rounded-lg border border-border/80 py-1 shadow-lg"
                    >
                      {filtered.length === 0 && (
                        <li className="px-3 py-2 text-xs text-muted-foreground">
                          {optionsError || '没有匹配的贷款申请'}
                        </li>
                      )}
                      {filtered.map((item) => {
                        const active = item.applicationId === applicationId
                        return (
                          <li key={item.applicationId}>
                            <button
                              type="button"
                              role="option"
                              aria-selected={active}
                              className={cn(
                                'flex w-full cursor-pointer flex-col px-3 py-2 text-left text-xs transition-colors',
                                active ? 'bg-brand-soft text-brand' : 'hover:bg-muted',
                              )}
                              onClick={() => pickApplication(item)}
                            >
                              <span className="font-mono font-medium">{item.applicationId}</span>
                              <span className="text-muted-foreground">
                                {item.enterpriseName || '（无名称）'}
                                {` · ${item.enterpriseId} · 申请 ${item.applyAmount || '—'} 万元 · ${item.loanTermMonths || '—'} 个月`}
                                {item.loanPurpose ? ` · ${item.loanPurpose}` : ''}
                              </span>
                            </button>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
              </div>
              <Button type="submit" className="h-10 cursor-pointer" disabled={loading || !applicationId}>
                {loading ? <Spinner /> : <SearchIcon />}
                {dim.slug === 'report' ? '生成报告' : '分析本步'}
              </Button>
            </div>
            {selected && (
              <p className="mt-1.5 text-[11px] text-muted-foreground">
                已选 {selected.applicationId} · 企业 {selected.enterpriseId}
                {selected.enterpriseName ? ` · ${selected.enterpriseName}` : ''}
                {` · 申请 ${selected.applyAmount || '—'} 万元`}
              </p>
            )}
          </div>
        </form>
      </Rise>

      <Rise delay={0.1}>
        <DependencyPanel
          dim={dim}
          enterpriseId={enterpriseId}
          applicationId={applicationId}
          loading={loading}
          onNavigate={onNavigate}
        />
      </Rise>

      <Rise delay={0.14}>
        <section className="surface-panel min-h-[320px] overflow-hidden rounded-2xl">
          <div className="flex items-center justify-between border-b border-border/70 bg-tech-soft/35 px-5 py-3">
            <h2 className="text-sm font-medium tracking-tight">
              {dim.slug === 'report' ? '报告结果' : '本步结果'}
            </h2>
            {result && (
              <span className={cn(
                'rounded-md border px-2 py-0.5 font-mono text-[11px] font-medium',
                result.status === 'ok' && 'border-success/30 bg-success/10 text-success',
                result.status === 'partial' && 'border-warning/30 bg-warning/10 text-warning',
                result.status === 'error' && 'border-destructive/30 bg-destructive/10 text-destructive',
              )}>
                {result.status === 'ok' ? '全部成功' : result.status === 'partial' ? '部分结果' : '失败'}
              </span>
            )}
          </div>
          <div className="px-5 py-4">
            <AnimatePresence mode="wait">
              {loading && !result && (
                <motion.div
                  key="loading"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex flex-col items-center gap-3 py-14 text-sm text-muted-foreground"
                >
                  <motion.div
                    className={cn('flex size-12 items-center justify-center rounded-2xl border', theme.chip)}
                    animate={reduce ? undefined : { rotate: [0, 6, -6, 0], scale: [1, 1.04, 1] }}
                    transition={{ duration: 1.8, repeat: Infinity }}
                  >
                    <DimGlyph slug={dim.slug} className="size-6" />
                  </motion.div>
                  <p className="flex items-center gap-2">
                    <Spinner />
                    {dim.dependsOn.some((d) => d.used)
                      ? `正在纳入前置（${dim.dependsOn.filter((d) => d.used).map((d) => d.label).join('、')}）并跑本步…`
                      : `正在调用本步工具（${dim.tools.join(' · ')}）…`}
                  </p>
                </motion.div>
              )}
              {!loading && error && (
                <motion.p
                  key="error"
                  role="alert"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-sm text-destructive"
                >
                  {error}
                </motion.p>
              )}
              {!loading && !error && !result && (
                <motion.div
                  key="empty"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-xl border border-dashed px-4 py-14 text-center"
                >
                  <p className="text-sm text-muted-foreground">
                    {dim.slug === 'report'
                      ? '从下拉选择贷款申请后即可汇总并导出结构化尽调报告'
                      : '从下拉选择贷款申请后即可查看该角色的结构化结果'}
                  </p>
                  <p className="mt-2 font-mono text-[11px] text-muted-foreground/80">
                    {dim.step}. {dim.label} · 就绪
                  </p>
                </motion.div>
              )}
              {result && (
                <motion.div
                  key={`${dim.slug}:${result.applicationId}:${result.status}`}
                  initial={reduce ? false : { opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4 }}
                >
                  <StepResultView result={result} theme={dim.theme} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </section>
      </Rise>
    </div>
  )
}
