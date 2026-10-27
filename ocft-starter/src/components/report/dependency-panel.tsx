/**
 * 单步页的计算依赖说明：后步内部会重算前序结果，分析时把链路摊开，避免误以为「无依赖」。
 */
import { ArrowRightIcon, CheckIcon, CircleSlashIcon, Link2Icon } from 'lucide-react'

import { Spinner } from '@/components/ui/spinner'
import { reportPath, type ReportDim } from '@/lib/report-dims'
import { cn } from '@/lib/utils'

export function DependencyPanel({ dim, enterpriseId, applicationId, loading, onNavigate }: {
  dim: ReportDim
  enterpriseId: string
  applicationId: string
  loading: boolean
  onNavigate: (href: string) => void
}) {
  if (dim.dependsOn.length === 0) return null

  const used = dim.dependsOn.filter((d) => d.used)
  const unused = dim.dependsOn.filter((d) => !d.used)

  return (
    <section
      aria-label="计算依赖"
      className="surface-panel rounded-xl px-5 py-4"
    >
      <header className="flex flex-wrap items-center gap-2">
        <Link2Icon aria-hidden className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-medium">计算依赖</h2>
        {loading ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Spinner className="size-3" /> 正在纳入前置结果并跑本步…
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">
            不必先打开前序页；本步会在服务端同进程重算所需前置
          </span>
        )}
      </header>

      <ol className="mt-3 flex flex-wrap items-stretch gap-2">
        {dim.dependsOn.map((dep, index) => {
          const href = reportPath(dep.slug, { enterpriseId, applicationId })
          return (
            <li key={dep.slug} className="flex min-w-[10rem] flex-1 items-stretch gap-2">
              {index > 0 && (
                <ArrowRightIcon aria-hidden className="mt-4 size-3.5 shrink-0 self-start text-muted-foreground" />
              )}
              <button
                type="button"
                className={cn(
                  'flex w-full cursor-pointer flex-col rounded-lg border px-3 py-2.5 text-left transition-colors',
                  dep.used
                    ? loading
                      ? 'border-info/40 bg-info/5'
                      : 'border-brand/30 bg-brand-soft/40 hover:bg-brand-soft'
                    : 'border-dashed border-border/80 bg-muted/30 opacity-80 hover:opacity-100',
                )}
                onClick={() => onNavigate(href)}
                title={`打开「${dep.label}」单步页`}
              >
                <span className="flex items-center gap-1.5 text-xs font-medium">
                  {dep.used
                    ? (loading
                      ? <Spinner className="size-3" />
                      : <CheckIcon aria-hidden className="size-3.5 text-success" />)
                    : <CircleSlashIcon aria-hidden className="size-3.5 text-muted-foreground" />}
                  {REPORT_STEP[dep.slug]}. {dep.label}
                </span>
                <span className="mt-1 text-[11px] leading-snug text-muted-foreground">{dep.how}</span>
                <span className={cn(
                  'mt-1.5 w-fit rounded px-1.5 py-0.5 font-mono text-[10px]',
                  dep.used ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground',
                )}>
                  {dep.used ? (loading ? '纳入中' : '本步已用') : '本步不用'}
                </span>
              </button>
            </li>
          )
        })}
        <li className="flex min-w-[10rem] flex-1 items-stretch gap-2">
          <ArrowRightIcon aria-hidden className="mt-4 size-3.5 shrink-0 self-start text-muted-foreground" />
          <div className={cn(
            'flex w-full flex-col rounded-lg border px-3 py-2.5',
            loading ? 'border-brand/50 bg-brand-soft' : 'border-foreground/15 bg-card',
          )}>
            <span className="flex items-center gap-1.5 text-xs font-medium">
              {loading ? <Spinner className="size-3" /> : <CheckIcon aria-hidden className="size-3.5 text-brand" />}
              {dim.step}. {dim.label}
            </span>
            <span className="mt-1 text-[11px] leading-snug text-muted-foreground">
              当前步骤 · {dim.tools.join(' · ')}
            </span>
            <span className="mt-1.5 w-fit rounded bg-brand/10 px-1.5 py-0.5 font-mono text-[10px] text-brand">
              {loading ? '分析中' : '本步'}
            </span>
          </div>
        </li>
      </ol>

      <p className="mt-3 text-xs text-muted-foreground">
        实际参与本步：{used.map((d) => d.label).join('、') || '无前置'}
        {unused.length > 0 && (
          <>；菜单上在前但本步不读：{unused.map((d) => d.label).join('、')}</>
        )}
        。点卡片可跳到对应单步页对照。
      </p>
    </section>
  )
}

const REPORT_STEP: Record<ReportDim['dependsOn'][number]['slug'], number> = {
  business: 1,
  finance: 2,
  opinion: 3,
  fraud: 4,
  'credit-risk': 5,
  report: 6,
}
