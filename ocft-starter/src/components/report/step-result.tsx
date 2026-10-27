/**
 * 单步工具结果的结构化展示：按工商 / 财务 / 舆情 / 反欺诈检测 / 额度测算 / 报告版式渲染，
 * 不再默认堆原始 JSON；底部可展开原始数据便于联调。
 */
import { ChevronDownIcon, FileJsonIcon } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { useState, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { downloadDdReportJson } from '@/lib/dd-report-export'

import { THEME_CLASS } from '@/components/report/dim-theme'
import {
  CountUp,
  MetricTile,
  ScoreRing,
  Stagger,
  StaggerItem,
} from '@/components/report/dim-visuals'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import type { ReportDim } from '@/lib/report-dims'
import type { DdStepResult, DdStepToolResult } from '@/lib/types'
import { cn } from '@/lib/utils'

type Dict = Record<string, unknown>
type Theme = ReportDim['theme']

function isDict(value: unknown): value is Dict {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function text(value: unknown, fallback = '—'): string {
  if (value == null || value === '') return fallback
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

function num(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && !Number.isNaN(Number(value))) return Number(value)
  return null
}

function formatNumber(value: unknown, digits = 2): string {
  const n = num(value)
  if (n == null) return text(value)
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

function formatRatio(value: unknown): string {
  const n = num(value)
  if (n == null) return text(value)
  if (Math.abs(n) <= 2) return `${(n * 100).toFixed(2)}%`
  return formatNumber(n)
}

function formatMaybeRatio(value: unknown, key: string): string {
  if (/ratio|margin|roe|roa|yoy|cagr/i.test(key)) return formatRatio(value)
  return formatNumber(value)
}

function Chip({ children, tone = 'muted' }: {
  children: ReactNode
  tone?: 'ok' | 'warn' | 'bad' | 'muted' | 'info'
}) {
  return (
    <span className={cn(
      'inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium',
      tone === 'ok' && 'bg-success/10 text-success',
      tone === 'warn' && 'bg-warning/10 text-warning',
      tone === 'bad' && 'bg-destructive/10 text-destructive',
      tone === 'info' && 'bg-info/10 text-info',
      tone === 'muted' && 'bg-muted text-muted-foreground',
    )}>
      {children}
    </span>
  )
}

function Section({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</h4>
        {action}
      </div>
      {children}
    </div>
  )
}

function SimpleTable({ headers, rows }: { headers: string[]; rows: ReactNode[][] }) {
  if (rows.length === 0) {
    return <p className="text-xs text-muted-foreground">暂无数据</p>
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-border/70">
      <table className="w-full min-w-max border-collapse text-left text-xs">
        <thead>
          <tr className="border-b bg-muted/40">
            {headers.map((h) => (
              <th key={h} className="px-2.5 py-2 font-medium text-muted-foreground whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b last:border-0 transition-colors hover:bg-muted/30">
              {row.map((cell, j) => (
                <td key={j} className="px-2.5 py-2 align-top whitespace-nowrap">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RawJson({ value }: { value: unknown }) {
  return (
    <Collapsible className="rounded-xl border border-border/70">
      <CollapsibleTrigger className="group flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2 text-left text-xs text-muted-foreground hover:bg-muted/40">
        <span>原始 JSON（调试）</span>
        <ChevronDownIcon className="size-3.5 shrink-0 transition-transform group-aria-expanded:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <pre className="max-h-80 overflow-auto border-t bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
          {JSON.stringify(value, null, 2)}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  )
}

const SUBJECT_LABELS: Record<string, string> = {
  revenue: '营业收入',
  netProfit: '净利润',
  totalAssets: '总资产',
  totalLiabilities: '总负债',
  ownersEquity: '所有者权益',
  operatingCashflow: '经营现金流',
  accountsReceivable: '应收账款',
  inventory: '存货',
  otherReceivable: '其他应收款',
  shortTermLoan: '短期借款',
  longTermLoan: '长期借款',
  interestBearingDebt: '有息负债',
  rdExpense: '研发费用',
  salesExpense: '销售费用',
  adminExpense: '管理费用',
  financeExpense: '财务费用',
  auditOpinion: '审计意见',
}

const GROWTH_LABELS: Record<string, string> = {
  revenueYoy: '营收同比',
  netProfitYoy: '净利同比',
  inventoryYoy: '存货同比',
  receivableYoy: '应收同比',
  revenueCagr: '营收 CAGR',
  netProfitCagr: '净利 CAGR',
}

const DIM_LABELS: Record<string, string> = {
  financial: '财务',
  solvency: '偿债',
  stability: '稳定性',
  judicial: '司法舆情',
  fraud: '反欺诈检测',
}

function findingTone(level: unknown): 'bad' | 'warn' | 'muted' {
  if (level === 'block') return 'bad'
  if (level === 'warn') return 'warn'
  return 'muted'
}

function BusinessBody({ data, theme }: { data: Dict; theme: Theme }) {
  const findings = asList(data.findings).filter(isDict)
  const paid = num(data.paidInRatio)
  return (
    <div className="space-y-5">
      <Stagger className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <MetricTile tone={theme} label="经营状态" value={text(data.businessStatus)} />
        <MetricTile
          tone={theme}
          label="实缴比例"
          value={paid == null ? text(data.paidInRatio) : (
            <span className="tabular-nums">
              <CountUp value={Math.abs(paid) <= 2 ? paid * 100 : paid} digits={1} />%
            </span>
          )}
        />
        <MetricTile tone={theme} label="实控人" value={text(data.actualController)} />
        <MetricTile
          tone={theme}
          label="实控=大股东"
          value={data.controllerMatchesTopShareholder ? <Chip tone="ok">一致</Chip> : <Chip tone="warn">不一致</Chip>}
        />
        <MetricTile tone={theme} label="关联企业（登记/明细）" value={`${text(data.relatedEnterpriseCountDeclared)} / ${text(data.relatedEnterpriseCountActual)}`} />
        <MetricTile tone={theme} label="第一大股东" value={text(data.topShareholder)} />
        <MetricTile tone={theme} label="担保逾期笔数" value={text(data.guaranteeOverdueCount, '0')} />
        <MetricTile tone={theme} label="担保圈关联数" value={text(data.guaranteeCircleCount, '0')} />
      </Stagger>
      <Section
        title="Findings"
        action={<Chip tone={findings.length ? 'warn' : 'ok'}>{findings.length ? `${findings.length} 条` : '无异常'}</Chip>}
      >
        {findings.length === 0 ? (
          <p className="rounded-xl border border-success/25 bg-success/5 px-3 py-3 text-sm text-success">未触发工商异常规则。</p>
        ) : (
          <Stagger className="space-y-1.5">
            {findings.map((item, i) => (
              <StaggerItem key={i}>
                <li className="flex list-none flex-wrap items-start gap-2 rounded-xl border border-border/70 bg-card/60 px-3 py-2.5 text-sm">
                  <Chip tone={findingTone(item.level)}>{text(item.code)}</Chip>
                  <Chip tone={findingTone(item.level)}>{text(item.level)}</Chip>
                  <span className="min-w-0 flex-1">{text(item.detail)}</span>
                </li>
              </StaggerItem>
            ))}
          </Stagger>
        )}
      </Section>
    </div>
  )
}

function FinanceBody({ data, theme }: { data: Dict; theme: Theme }) {
  const years = asList(data.years).filter(isDict)
  const growth = isDict(data.growth) ? data.growth : {}
  const subjectKeys = years[0] && isDict(years[0].subjects)
    ? Object.keys(years[0].subjects as Dict).filter((k) => k !== 'auditOpinion')
    : Object.keys(SUBJECT_LABELS).filter((k) => k !== 'auditOpinion')
  const metricNames = new Map<string, string>()
  for (const year of years) {
    const metrics = isDict(year.metrics) ? year.metrics : {}
    for (const [key, spec] of Object.entries(metrics)) {
      if (isDict(spec) && typeof spec.name === 'string') metricNames.set(key, spec.name)
    }
  }

  return (
    <div className="space-y-5">
      <Stagger className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <MetricTile tone={theme} label="单位" value={text(data.unit)} />
        <MetricTile tone={theme} label="最新财年" value={text(data.latestYear)} />
        <MetricTile tone={theme} label="截取时点 asOf" value={text(data.asOf)} />
        <MetricTile tone={theme} label="企业" value={text(data.enterpriseId)} />
      </Stagger>
      {data.denominatorNote ? (
        <p className="text-xs text-muted-foreground">{text(data.denominatorNote)}</p>
      ) : null}

      <Section title="增长">
        <Stagger className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          {Object.entries(growth).map(([key, value]) => (
            <MetricTile key={key} tone={theme} label={GROWTH_LABELS[key] ?? key} value={formatRatio(value)} />
          ))}
        </Stagger>
      </Section>

      <Section title={`科目（${text(data.unit)}）`}>
        <SimpleTable
          headers={['科目', ...years.map((y) => String(y.year))]}
          rows={subjectKeys.map((key) => [
            SUBJECT_LABELS[key] ?? key,
            ...years.map((y) => {
              const subjects = isDict(y.subjects) ? y.subjects : {}
              return formatNumber(subjects[key])
            }),
          ])}
        />
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
          {years.map((y) => {
            const subjects = isDict(y.subjects) ? y.subjects : {}
            const check = isDict(y.balanceCheck) ? y.balanceCheck : {}
            return (
              <span key={String(y.year)} className="inline-flex items-center gap-1.5">
                {String(y.year)} 审计：{text(subjects.auditOpinion)}
                <Chip tone={check.balanced ? 'ok' : 'bad'}>
                  勾稽{check.balanced ? '平衡' : `差额 ${formatNumber(check.gap)}`}
                </Chip>
              </span>
            )
          })}
        </div>
      </Section>

      <Section title="业务比率">
        <SimpleTable
          headers={['指标', ...years.map((y) => String(y.year)), '标记']}
          rows={[...metricNames.entries()].map(([key, name]) => {
            const flags = years.map((y) => {
              const metrics = isDict(y.metrics) ? y.metrics : {}
              const spec = isDict(metrics[key]) ? metrics[key] : null
              return spec?.flag
            }).filter(Boolean)
            return [
              name,
              ...years.map((y) => {
                const metrics = isDict(y.metrics) ? y.metrics : {}
                const spec = isDict(metrics[key]) ? metrics[key] : null
                return formatMaybeRatio(spec?.value, key)
              }),
              flags.length
                ? <Chip key="flag" tone="warn">{flags.map(String).join(' / ')}</Chip>
                : <Chip key="flag" tone="ok">正常</Chip>,
            ]
          })}
        />
      </Section>
    </div>
  )
}

function OpinionBody({ data, theme }: { data: Dict; theme: Theme }) {
  const events = asList(data.events).filter(isDict)
  const lawsuits = asList(data.lawsuits).filter(isDict)
  const labels = asList(data.labels).map(String)
  const health = num(data.healthScore) ?? 0
  const risk = num(data.opinionRiskScore) ?? 0
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-6 rounded-2xl border border-border/70 bg-gradient-to-br from-card/90 to-warning/5 px-4 py-4">
        <ScoreRing score={health} label="健康分" tone={theme} />
        <ScoreRing score={risk} max={Math.max(risk, 100)} label="舆情风险" tone="rose" />
        <Stagger className="grid min-w-[12rem] flex-1 grid-cols-2 gap-2.5">
          <MetricTile tone={theme} label="未结被告金额" value={formatNumber(data.openDefendantAmount)} />
          <MetricTile tone={theme} label="asOf" value={text(data.asOf)} />
          <MetricTile tone={theme} label="企业" value={text(data.enterpriseId)} />
          <MetricTile tone={theme} label="事件 / 涉诉" value={`${events.length} / ${lawsuits.length}`} />
        </Stagger>
      </div>
      <Section title="标签">
        {labels.length === 0
          ? <p className="text-sm text-muted-foreground">无标签</p>
          : (
            <Stagger className="flex flex-wrap gap-1.5">
              {labels.map((label) => (
                <StaggerItem key={label}>
                  <Chip tone="info">{label}</Chip>
                </StaggerItem>
              ))}
            </Stagger>
          )}
      </Section>
      <Section title={`舆情事件（${events.length}）`}>
        <SimpleTable
          headers={['日期', '类型', '情感', '影响', '得分', '内容', '来源']}
          rows={events.map((e) => [
            text(e.eventDate),
            text(e.eventType),
            text(e.sentiment),
            text(e.impactLevel),
            formatNumber(e.points),
            <span key="c" className="max-w-[18rem] whitespace-normal">{text(e.eventContent)}</span>,
            text(e.eventSource),
          ])}
        />
      </Section>
      <Section title={`涉诉（${lawsuits.length}）`}>
        <SimpleTable
          headers={['案号', '状态', '角色', '金额', '分桶', '得分']}
          rows={lawsuits.map((row) => [
            text(row.caseId),
            text(row.caseStatus),
            text(row.litigationRole),
            formatNumber(row.amount),
            text(row.bucket),
            text(row.points),
          ])}
        />
      </Section>
    </div>
  )
}

function FraudBody({ data, theme }: { data: Dict; theme: Theme }) {
  const rules = asList(data.rules).filter(isDict)
  const hits = asList(data.hitRuleIds).map(String)
  const hitCount = num(data.hitCount) ?? hits.length
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-6 rounded-2xl border border-destructive/20 bg-gradient-to-br from-card/90 to-destructive/5 px-4 py-4">
        <ScoreRing score={hitCount} max={Math.max(rules.length, hitCount, 1)} label="命中数" tone={theme} />
        <div className="min-w-0 flex-1 space-y-2">
          <p className="text-sm font-medium text-foreground">本步如何吃前序</p>
          <ul className="list-disc space-y-0.5 pl-4 text-xs leading-relaxed text-muted-foreground">
            <li><span className="text-foreground">财报解析</span>（内部重算）：F01–F05 用科目与增长</li>
            <li><span className="text-foreground">工商侧事实</span>：F06 用关联企业数与担保圈</li>
            <li><span className="text-foreground">舆情扫描</span>：本步规则不读；健康分在额度测算才进维度分</li>
          </ul>
          <p className="text-xs text-muted-foreground">
            命中规则：{hits.length ? hits.join('、') : '无'}
          </p>
        </div>
      </div>
      <Section title="规则明细">
        <Stagger className="space-y-2">
          {rules.map((rule) => (
            <StaggerItem key={text(rule.ruleId)}>
              <div className={cn(
                'rounded-xl border px-3 py-2.5 transition-colors',
                rule.hit ? 'border-destructive/40 bg-destructive/5' : 'border-border/70 bg-card/60',
              )}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-medium">{text(rule.ruleId)}</span>
                  <span className="text-sm font-medium">{text(rule.name)}</span>
                  {rule.hit
                    ? <Chip tone="bad">命中</Chip>
                    : <Chip tone="ok">未命中</Chip>}
                  <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                    {formatNumber(rule.value, 4)} / 阈值 {formatNumber(rule.threshold, 4)}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{text(rule.detail)}</p>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      </Section>
    </div>
  )
}

function RatingBody({ data, theme }: { data: Dict; theme: Theme }) {
  const dimensions = asList(data.dimensions).filter(isDict)
  const vetoes = asList(data.vetoes)
  const score = num(data.score) ?? 0
  const level = String(data.riskLevel ?? '')
  const levelTone: Theme = level.includes('高') ? 'rose' : level.includes('中') ? 'amber' : 'teal'
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-6 rounded-2xl border border-brand/20 bg-gradient-to-br from-card/90 to-brand-soft/40 px-4 py-4">
        <ScoreRing score={score} max={Math.max(score, 100)} label="风险点数" tone={levelTone} />
        <Stagger className="grid min-w-[14rem] flex-1 grid-cols-2 gap-2.5">
          <MetricTile
            tone={theme}
            label="风险等级"
            value={<Chip tone={level.includes('高') ? 'bad' : level.includes('中') ? 'warn' : 'ok'}>{text(data.riskLevel)}</Chip>}
          />
          <MetricTile
            tone={theme}
            label="人工复核"
            value={data.needsManualReview ? <Chip tone="warn">需要</Chip> : <Chip tone="ok">否</Chip>}
          />
          <MetricTile tone={theme} label="企业" value={text(data.enterpriseId)} />
          <MetricTile tone={theme} label="申请" value={text(data.applicationId)} />
        </Stagger>
      </div>
      <p className="text-xs text-muted-foreground">
        本步吃前序：财务→财务/偿债；工商→稳定性；舆情健康分→司法舆情；反欺诈检测命中→欺诈维度与否决
      </p>
      <Section title="评分卡指标（点数制）">
        <Stagger className="space-y-2">
          {dimensions.map((d) => {
            const points = num(d.points) ?? 0
            const maxPoints = num(d.maxPoints) ?? 0
            const pct = maxPoints > 0 ? Math.min(100, (points / maxPoints) * 100) : 0
            return (
              <StaggerItem key={text(d.dimension ?? d.name)}>
                <div className="rounded-xl border border-border/70 bg-card/60 px-3 py-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="font-medium">{text(d.name ?? DIM_LABELS[String(d.dimension)] ?? d.dimension)}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {d.points == null ? '—' : `${formatNumber(d.points, 0)} / ${formatNumber(d.maxPoints, 0)}`}
                      {' · '}
                      {typeof d.value === 'boolean' ? text(d.value) : formatNumber(d.value, 4)}
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                    <motion.div
                      className={cn('h-full rounded-full', THEME_CLASS[theme].bar)}
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                    />
                  </div>
                </div>
              </StaggerItem>
            )
          })}
        </Stagger>
      </Section>
      <Section title="一票否决">
        {vetoes.length === 0
          ? <p className="rounded-xl border border-success/25 bg-success/5 px-3 py-3 text-sm text-success">无否决项</p>
          : (
            <ul className="space-y-1 text-sm">
              {vetoes.map((item, i) => (
                <li key={i} className="rounded-xl border border-destructive/30 px-3 py-2 text-destructive">
                  {isDict(item) ? text(item.detail ?? item.code ?? item) : text(item)}
                </li>
              ))}
            </ul>
          )}
      </Section>
    </div>
  )
}

function ReportBody({ data, theme }: { data: Dict; theme: Theme }) {
  const sections = isDict(data.sections) ? data.sections : {}
  const overview = isDict(sections.overview) ? sections.overview : {}
  const risk = isDict(sections.riskAlerts) ? sections.riskAlerts : {}
  const credit = isDict(sections.creditSuggestion) ? sections.creditSuggestion : {}
  const conditions = isDict(sections.riskConditions) ? sections.riskConditions : {}
  const findings = asList(overview.findings)
  const conditionLines = asList(conditions.conditions).map(String)
  const level = String(risk.riskLevel ?? data.riskLevel ?? '')
  // 企业主体尽调：展示建议额度，隐藏申请额度；贷款申请尽调并列两者
  const enterpriseScope = data.scope === 'enterprise'
  const [busy, setBusy] = useState<'json' | null>(null)
  const [exportError, setExportError] = useState('')

  const runExport = () => {
    setBusy('json')
    setExportError('')
    try {
      downloadDdReportJson(data)
    } catch {
      setExportError('导出 JSON 失败')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-brand/25 bg-gradient-to-br from-brand-soft/70 via-card to-tech-soft/30 px-4 py-4">
        <Stagger className="grid min-w-[16rem] flex-1 grid-cols-2 gap-2.5 sm:grid-cols-4">
          <MetricTile
            tone={theme}
            label="风险评级"
            value={<Chip tone={level.includes('高') ? 'bad' : level.includes('中') ? 'warn' : 'ok'}>{text(risk.riskLevel ?? data.riskLevel)}</Chip>}
          />
          <MetricTile
            tone={theme}
            label="建议授信额度"
            value={`${formatNumber(credit.suggestedCreditAmount ?? data.suggestedCreditAmount)} ${text(credit.unit, '')}`.trim()}
          />
          {!enterpriseScope && (
            <MetricTile
              tone={theme}
              label="申请贷款额度"
              value={`${formatNumber(credit.applyAmount)} ${text(credit.unit, '')}`.trim()}
            />
          )}
          <MetricTile tone={theme} label="企业" value={text(data.enterpriseId)} />
          {!enterpriseScope && (
            <MetricTile tone={theme} label="申请" value={text(data.applicationId)} />
          )}
        </Stagger>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="cursor-pointer"
            disabled={busy !== null}
            onClick={runExport}
          >
            <FileJsonIcon />
            {busy === 'json' ? '导出中…' : '导出 JSON'}
          </Button>
        </div>
      </div>
      {exportError ? <p className="text-xs text-destructive">{exportError}</p> : null}
      <Section title="尽调结论">
        <p className="rounded-xl border border-border/70 bg-card/70 px-3 py-3 text-sm leading-relaxed">
          {text(data.dueDiligenceConclusion, '暂无结论摘要')}
        </p>
      </Section>
      <Section title="企业概况">
        <Stagger className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <MetricTile tone={theme} label="行业" value={text(overview.industry)} />
          <MetricTile tone={theme} label="经营状态" value={text(overview.businessStatus)} />
          <MetricTile tone={theme} label="成立日期" value={text(overview.establishDate)} />
          <MetricTile tone={theme} label="工商发现数" value={String(findings.length)} />
        </Stagger>
        {findings.length > 0 && (
          <ul className="mt-2 space-y-1 text-sm">
            {findings.map((item, i) => (
              <li key={i} className="rounded-lg border border-border/70 px-3 py-2">
                {isDict(item) ? text(item.detail ?? item.code ?? item) : text(item)}
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="风险提示摘要">
        <Stagger className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <MetricTile tone={theme} label="评分" value={text(risk.score)} />
          <MetricTile tone={theme} label="人工复核" value={text(risk.needsManualReview)} />
          <MetricTile tone={theme} label="反欺诈检测命中" value={asList(risk.fraudHits).length ? asList(risk.fraudHits).map(String).join('、') : '无'} />
          <MetricTile tone={theme} label="舆情标签" value={asList(risk.opinionLabels).length ? asList(risk.opinionLabels).map(String).join('、') : '无'} />
        </Stagger>
      </Section>
      <Section title="风控条件">
        {conditionLines.length === 0
          ? <p className="text-sm text-muted-foreground">无附加条件</p>
          : (
            <ul className="list-disc space-y-1 pl-4 text-sm">
              {conditionLines.map((item, i) => <li key={i}>{item}</li>)}
            </ul>
          )}
      </Section>
    </div>
  )
}

function CreditBody({ data, theme }: { data: Dict; theme: Theme }) {
  const steps = asList(data.steps).filter(isDict)
  const conditions = asList(data.conditions).map(String)
  const assumptions = asList(data.assumptions).map(String)
  const exposures = isDict(data.exposures) ? data.exposures : {}
  const amount = num(data.suggestedCreditAmount)
  const reduce = useReducedMotion()
  return (
    <div className="space-y-5">
      <motion.div
        className="relative overflow-hidden rounded-2xl border border-brand/30 bg-gradient-to-br from-brand-soft/80 via-card to-tech-soft/40 px-5 py-5"
        initial={reduce ? false : { scale: 0.98, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.45 }}
      >
        {!reduce && (
          <motion.div
            aria-hidden
            className="pointer-events-none absolute -right-6 top-0 size-32 rounded-full bg-brand/20 blur-2xl"
            animate={{ opacity: [0.4, 0.75, 0.4] }}
            transition={{ duration: 3.2, repeat: Infinity }}
          />
        )}
        <p className="text-xs font-medium tracking-wide text-brand uppercase">建议额度</p>
        <p className="mt-1 flex flex-wrap items-baseline gap-2">
          <span className="text-3xl font-semibold tracking-tight text-brand sm:text-4xl">
            {amount == null
              ? text(data.suggestedCreditAmount)
              : <CountUp value={amount} digits={0} />}
          </span>
          <span className="text-sm text-muted-foreground">{text(data.unit)}</span>
        </p>
        <Stagger className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <MetricTile tone={theme} label="风险等级" value={text(data.riskLevel)} />
          <MetricTile tone={theme} label="期限（月）" value={text(data.termMonths)} />
          <MetricTile tone={theme} label="利率方向" value={text(data.rateDirection)} />
          <MetricTile tone={theme} label="担保方式" value={text(data.guaranteeType)} />
        </Stagger>
      </motion.div>
      <Stagger className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <MetricTile tone={theme} label="申请" value={text(data.applicationId)} />
        <MetricTile tone={theme} label="财年" value={text(data.financialYear)} />
        <MetricTile tone={theme} label="政策版本" value={text(data.policyVersion)} />
        <MetricTile tone={theme} label="存量贷款余额" value={formatNumber(exposures.existingLoanBalance)} />
        <MetricTile tone={theme} label="对外担保" value={formatNumber(exposures.externalGuaranteeAmount)} />
      </Stagger>
      <Section title="测算步骤">
        <SimpleTable
          headers={['步骤', '公式', '值']}
          rows={steps.map((step) => [
            text(step.step),
            <span key="f" className="max-w-[22rem] whitespace-normal font-mono text-[11px]">{text(step.formula)}</span>,
            text(step.value),
          ])}
        />
      </Section>
      <Section title="风控条件">
        {conditions.length === 0
          ? <p className="text-sm text-muted-foreground">无附加条件</p>
          : (
            <ul className="list-disc space-y-1 pl-4 text-sm">
              {conditions.map((item, i) => <li key={i}>{item}</li>)}
            </ul>
          )}
      </Section>
      {assumptions.length > 0 && (
        <Section title="假设">
          <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
            {assumptions.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </Section>
      )}
    </div>
  )
}

function ToolDataBody({ toolName, data, theme }: { toolName: string; data: unknown; theme: Theme }) {
  if (!isDict(data)) {
    return <p className="text-sm text-muted-foreground">无可展示的结构化字段</p>
  }
  switch (toolName) {
    case 'verify_business_info':
      return <BusinessBody data={data} theme={theme} />
    case 'analyze_financials':
      return <FinanceBody data={data} theme={theme} />
    case 'scan_public_opinion':
      return <OpinionBody data={data} theme={theme} />
    case 'detect_fraud_signals':
      return <FraudBody data={data} theme={theme} />
    case 'rate_risk':
      return <RatingBody data={data} theme={theme} />
    case 'calc_credit_limit':
      return <CreditBody data={data} theme={theme} />
    case 'build_dd_report':
      return <ReportBody data={data} theme={theme} />
    default:
      return <p className="text-sm text-muted-foreground">未知工具，请展开原始 JSON。</p>
  }
}

const TOOL_TITLE: Record<string, string> = {
  verify_business_info: '工商 Agent · 核验结果',
  analyze_financials: '财务 Agent · 分析结果',
  scan_public_opinion: '舆情 Agent · 扫描结果',
  detect_fraud_signals: '反欺诈检测 Agent · 规则结果',
  rate_risk: '评级 Agent · 风险评级',
  calc_credit_limit: '授信 · 建议额度',
  build_dd_report: '尽调报告 · 结构化汇总',
}

const TOOL_THEME: Record<string, Theme> = {
  verify_business_info: 'teal',
  analyze_financials: 'sky',
  scan_public_opinion: 'amber',
  detect_fraud_signals: 'rose',
  rate_risk: 'orange',
  calc_credit_limit: 'orange',
  build_dd_report: 'orange',
}

function StatusChip({ status }: { status: DdStepToolResult['status'] }) {
  const map = {
    ok: { tone: 'ok' as const, label: '成功' },
    error: { tone: 'bad' as const, label: '失败' },
    skipped: { tone: 'muted' as const, label: '已跳过' },
  }
  const item = map[status]
  return <Chip tone={item.tone}>{item.label}</Chip>
}

function ToolPanel({ tool, theme }: { tool: DdStepToolResult; theme: Theme }) {
  const reduce = useReducedMotion()
  const panelTheme = TOOL_THEME[tool.toolName] ?? theme
  const accent = THEME_CLASS[panelTheme]
  return (
    <motion.article
      className="overflow-hidden rounded-2xl border border-border/70 bg-card/70 shadow-[inset_0_1px_0_rgb(255_255_255/0.45)]"
      initial={reduce ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className={cn('flex flex-wrap items-center gap-2 border-b px-4 py-2.5', accent.soft)}>
        <span aria-hidden className={cn('h-5 w-1 rounded-full', accent.bar)} />
        <h3 className="text-sm font-medium">{TOOL_TITLE[tool.toolName] ?? tool.toolName}</h3>
        <StatusChip status={tool.status} />
        <span className="font-mono text-[11px] text-muted-foreground">{tool.toolName}</span>
        {tool.message && <span className="text-xs text-muted-foreground">{tool.message}</span>}
        {tool.errorCode && <Chip tone="bad">{tool.errorCode}</Chip>}
      </div>
      <div className="space-y-3 px-4 py-4">
        {tool.data != null ? (
          <>
            <ToolDataBody toolName={tool.toolName} data={tool.data} theme={panelTheme} />
            <RawJson value={tool.data} />
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            {tool.errorCode ? `${tool.errorCode}` : '无数据'}
            {tool.message ? ` · ${tool.message}` : ''}
          </p>
        )}
      </div>
    </motion.article>
  )
}

export function StepResultView({ result, theme = 'orange' }: { result: DdStepResult; theme?: Theme }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>{result.note}</span>
        {result.enterpriseId && <span>企业 {result.enterpriseId}</span>}
        {result.applicationId && <span>申请 {result.applicationId}</span>}
      </div>
      {result.tools.map((tool) => (
        <ToolPanel key={tool.toolName} tool={tool} theme={theme} />
      ))}
    </div>
  )
}
