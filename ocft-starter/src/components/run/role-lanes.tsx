/**
 * 多 Agent 协作视图（尽调场景，ADR-0008）：主控计划 → 工商 / 财报 / 舆情并行 → 反欺诈 → 评级授信 → 报告 → 事实校验。
 * 每个状态都来自后端真实事件（plan_ready / role_started / role_finished / verify_finished），不补造进度。
 */
import {
  BotIcon,
  CheckCircle2Icon,
  CircleAlertIcon,
  CircleDashedIcon,
  CircleSlashIcon,
  FileCheck2Icon,
  ShieldCheckIcon,
  SparklesIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'

import { Spinner } from '@/components/ui/spinner'
import { DD_ROLES, ROLE_STATUS_META, TONE_CLASS, formatMs, parallelProbeDone } from '@/lib/format'
import type { RoleStatus, RunEvent } from '@/lib/types'
import { cn } from '@/lib/utils'

type LaneState = keyof typeof ROLE_STATUS_META

interface Lane {
  role: string
  name: string
  duty: string
  state: LaneState
  durationMs?: number
  llm?: boolean
  evidenceCount?: number
  errorCode?: string | null
  keyFindings: string[]
}

type PlanEvent = Extract<RunEvent, { type: 'plan_ready' }>
type VerifyEvent = Extract<RunEvent, { type: 'verify_finished' }>

function buildLanes(events: RunEvent[], live: boolean): { plan: PlanEvent | null; lanes: Lane[]; verify: VerifyEvent[] } {
  const plan = (events.find((e) => e.type === 'plan_ready') as PlanEvent | undefined) ?? null
  const planned = new Set(plan?.plan.roles ?? [])
  const started = new Set<string>()
  const finished = new Map<string, Extract<RunEvent, { type: 'role_finished' }>>()
  for (const e of events) {
    if (e.type === 'role_started') started.add(e.role)
    if (e.type === 'role_finished') finished.set(e.role, e)
  }
  const lanes = DD_ROLES.map(({ role, name, duty }): Lane => {
    const done = finished.get(role)
    if (done) {
      return {
        role, name: done.name || name, duty, state: done.status as RoleStatus,
        durationMs: done.durationMs, llm: done.llm, evidenceCount: done.evidenceCount,
        errorCode: done.errorCode, keyFindings: Array.isArray(done.keyFindings) ? done.keyFindings : [],
      }
    }
    let state: LaneState = 'waiting'
    if (!planned.has(role)) state = 'skipped'
    else if (started.has(role)) state = live ? 'running' : 'failed'
    else if (!live) state = 'failed'
    return { role, name, duty, state, keyFindings: [] }
  })
  const verify = events.filter((e): e is VerifyEvent => e.type === 'verify_finished')
  return { plan, lanes, verify }
}

const STATE_ICON: Record<LaneState, ReactNode> = {
  waiting: <CircleDashedIcon />,
  running: <Spinner />,
  ok: <CheckCircle2Icon />,
  degraded: <CircleAlertIcon />,
  skipped: <CircleSlashIcon />,
  failed: <CircleAlertIcon />,
}

function LaneCard({ lane }: { lane: Lane }) {
  const meta = ROLE_STATUS_META[lane.state]
  const dim = lane.state === 'skipped' || lane.state === 'waiting'
  return (
    <li
      className={cn(
        'min-w-0 rounded-lg border border-border/80 bg-card/70 p-2.5 text-sm transition-colors',
        lane.state === 'running' && 'border-info/60 bg-info/5',
        lane.state === 'degraded' && 'border-warning/50 bg-warning/5',
        lane.state === 'failed' && 'border-destructive/50 bg-destructive/5',
        lane.state === 'ok' && 'border-success/35 bg-success/5',
        dim && 'opacity-60',
      )}
      aria-label={`${lane.name}：${meta.label}`}
    >
      <div className="flex items-center gap-1.5">
        <span aria-hidden className="text-muted-foreground [&>svg]:size-4">{STATE_ICON[lane.state]}</span>
        <span className="truncate font-medium">{lane.name} Agent</span>
      </div>
      <span className={cn('mt-1 inline-flex h-5 items-center rounded-full px-2 text-xs font-medium', TONE_CLASS[meta.tone])}>
        {meta.label}
      </span>
      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{lane.duty}</p>
      {lane.durationMs != null && (
        <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          <span>{formatMs(lane.durationMs)}</span>
          {lane.llm && <span className="inline-flex items-center gap-0.5"><SparklesIcon aria-hidden className="size-3" />模型解读</span>}
          {!!lane.evidenceCount && <span className="inline-flex items-center gap-0.5"><FileCheck2Icon aria-hidden className="size-3" />{lane.evidenceCount} 条证据</span>}
        </p>
      )}
      {lane.errorCode && lane.state !== 'ok' && (
        <p className="mt-1 font-mono text-xs text-muted-foreground">{lane.errorCode}</p>
      )}
      {lane.keyFindings.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 border-t pt-1.5 text-xs">
          {lane.keyFindings.map((item, i) => (
            <li key={i} className="line-clamp-2" title={item}>· {item}</li>
          ))}
        </ul>
      )}
    </li>
  )
}

export function RoleLanes({ events, live }: { events: RunEvent[]; live: boolean }) {
  const { plan, lanes, verify } = buildLanes(events, live)
  if (!plan) return null
  const byRole = Object.fromEntries(lanes.map((l) => [l.role, l]))
  const lastVerify = verify.at(-1)
  const retries = verify.filter((v) => v.status === 'retry').length
  const target = plan.plan.target
  // 前三步没跑完时不展开下游空卡片，避免列表被「等待」撑高、滚下去什么也看不到。
  const showDownstream = parallelProbeDone(events) || !live
  // 单项追问时未调度的角色为「本次不需要」，不占卡片位。
  const parallel = ['business', 'finance', 'opinion']
    .map((r) => byRole[r])
    .filter((l): l is Lane => !!l && l.state !== 'skipped')
  const downstream = ['fraud', 'rating', 'report']
    .map((r) => byRole[r])
    .filter((l): l is Lane => !!l && l.state !== 'skipped')
  const waitingDownstream = showDownstream
    ? false
    : ['fraud', 'rating', 'report'].some((r) => byRole[r]?.state !== 'skipped')
  return (
    <section aria-label="多 Agent 协作" className="mb-3 space-y-2 rounded-xl border border-tech/20 bg-tech-soft/40 p-3">
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <BotIcon aria-hidden className="size-4 text-tech" />
        <span className="font-medium tracking-tight">主控 Agent 调度</span>
        <span className="text-xs text-muted-foreground">
          {plan.plan.mode === 'full' ? '完整尽调' : '单项追问'} · {target.applicationId ?? target.enterpriseId}
          {' '}· {plan.plan.roles.length} 个角色
        </span>
      </header>

      <div aria-live="polite" className="space-y-2">
        {parallel.length > 0 && (
          <div>
            <p className="mb-1 text-xs text-muted-foreground">
              {parallel.length === 3 ? '并行取证' : '取证'}
            </p>
            <ul
              className={cn(
                'grid grid-cols-1 gap-2',
                parallel.length === 2 && 'sm:grid-cols-2',
                parallel.length >= 3 && 'sm:grid-cols-3',
              )}
            >
              {parallel.map((lane) => <LaneCard key={lane.role} lane={lane} />)}
            </ul>
          </div>
        )}
        {showDownstream ? (
          <>
            {downstream.map((lane, i) => (
              <div key={lane.role}>
                {(parallel.length > 0 || i > 0) && (
                  <p aria-hidden className="mb-1 text-center text-xs text-muted-foreground">↓</p>
                )}
                <ul><LaneCard lane={lane} /></ul>
              </div>
            ))}
            {(lastVerify || (live && byRole.report?.state === 'ok')) && (
              <div
                className={cn(
                  'flex items-start gap-2 rounded-lg border bg-card p-2.5 text-sm',
                  lastVerify?.status === 'failed' && 'border-destructive/50',
                )}
              >
                <ShieldCheckIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0">
                  <p className="font-medium">
                    事实校验
                    {lastVerify
                      ? lastVerify.status === 'ok' ? '：通过' : lastVerify.status === 'failed' ? '：未通过，答案未发布' : '：发现问题，正在重写'
                      : '：进行中'}
                    {retries > 0 && <span className="ml-1 text-xs text-muted-foreground">（重写 {retries} 次）</span>}
                  </p>
                  <p className="text-xs text-muted-foreground">核对数字、风险评级、规则编号是否都来自本次计算</p>
                  {lastVerify && lastVerify.issues.length > 0 && (
                    <ul className="mt-1 space-y-0.5 text-xs text-destructive">
                      {lastVerify.issues.slice(0, 5).map((issue, i) => <li key={i}>· {issue}</li>)}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </>
        ) : waitingDownstream ? (
          <p className="text-center text-xs text-muted-foreground">取证完成后继续调度下游角色…</p>
        ) : null}
      </div>
      <p className="text-xs text-muted-foreground">
        数字由规则工具计算，角色 Agent 只做解读；角色配置见 <code className="font-mono">{plan.plan.configFile}</code>
      </p>
    </section>
  )
}
