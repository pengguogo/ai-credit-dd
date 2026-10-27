/**
 * 执行轨迹：由 SSE 事件逐条生成，执行中实时追加（shadcn Trace + Motion 入场）。
 * 每一行都对应后端一条真实事件，不补造步骤。
 */
import {
  BotIcon,
  CheckCircle2Icon,
  CircleAlertIcon,
  DatabaseIcon,
  FlagIcon,
  HelpCircleIcon,
  PlayIcon,
  ShieldCheckIcon,
  ShieldXIcon,
} from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'

import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceDescription,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from '@/components/ui/trace'
import { DD_ROLES, STATUS_META, categoryLabel, formatMs, toolLabel } from '@/lib/format'
import type { RunEvent, ToolTrace } from '@/lib/types'

interface Row {
  key: string
  icon: ReactNode
  title: string
  description?: string
  status?: 'running' | 'error' | 'pending'
  detail?: ReactNode
}

const ROLE_NAME = Object.fromEntries(DD_ROLES.map((r) => [r.role, r.name])) as Record<string, string>

function roleLabel(role: string, name?: string): string {
  return name || ROLE_NAME[role] || role
}

/** 计划中的步骤序号（1-based）；未知角色不编号 */
function roleStepIndex(events: RunEvent[], role: string): number | null {
  const plan = events.find((e): e is Extract<RunEvent, { type: 'plan_ready' }> => e.type === 'plan_ready')
  if (!plan) return null
  const i = plan.plan.roles.indexOf(role)
  return i >= 0 ? i + 1 : null
}

function stepTitle(step: number | null, name: string, suffix: string): string {
  return step != null ? `第 ${step} 步 · ${name}${suffix}` : `${name}${suffix}`
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-w-full overflow-x-auto rounded-md bg-muted px-2 py-1.5 font-mono text-xs text-foreground">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function buildRows(events: RunEvent[], traces: ToolTrace[], live: boolean): Row[] {
  const rows: Row[] = []
  const finishedSeq = new Set(events.filter((e) => e.type === 'tool_finished').map((e) => e.sequence))
  const finishedRoles = new Set(
    events.filter((e): e is Extract<RunEvent, { type: 'role_finished' }> => e.type === 'role_finished')
      .map((e) => e.role),
  )
  for (const e of events) {
    switch (e.type) {
      case 'run_started':
        rows.push({ key: `${e.eventIndex}`, icon: <PlayIcon />, title: '收到问题，开始执行' })
        break
      case 'compliance_checked':
        rows.push({
          key: `${e.eventIndex}`,
          icon: e.isClean ? <ShieldCheckIcon /> : <ShieldXIcon />,
          title: `${e.stage === 'input' ? '输入' : '输出'}合规检查${e.isClean ? '通过' : '未通过'}`,
          description: formatMs(e.durationMs),
          status: e.isClean ? undefined : 'error',
        })
        break
      case 'compliance_blocked':
        rows.push({
          key: `${e.eventIndex}`,
          icon: <ShieldXIcon />,
          title: `合规拦截：${categoryLabel(e.payload.category ?? 'other')}`,
          description: e.payload.stage === 'input' ? '未调用模型' : '答案未发布',
          status: 'error',
        })
        break
      case 'llm_call_finished': {
        const calls = e.toolCalls ?? []
        rows.push({
          key: `${e.eventIndex}`,
          icon: <BotIcon />,
          title: e.status === 'ok'
            ? `模型推理第 ${e.round} 轮${calls.length ? `，决定调用 ${calls.map(toolLabel).join('、')}` : '，生成回复'}`
            : `模型调用失败（${e.errorCode}）`,
          description: [formatMs(e.durationMs), e.totalTokens ? `${e.totalTokens} tokens` : '']
            .filter(Boolean).join(' · '),
          status: e.status === 'ok' ? undefined : 'error',
        })
        break
      }
      case 'tool_started':
        if (!finishedSeq.has(e.sequence)) {
          rows.push({
            key: `${e.eventIndex}`, icon: <DatabaseIcon />, title: `正在${toolLabel(e.toolName)}`,
            status: live ? 'running' : 'pending',
          })
        }
        break
      case 'tool_finished': {
        const trace = traces.find((t) => t.sequence === e.sequence)
        const isClarify = e.toolName === 'request_clarification'
        rows.push({
          key: `${e.eventIndex}`,
          icon: isClarify ? <HelpCircleIcon /> : <DatabaseIcon />,
          title: e.status === 'ok' ? toolLabel(e.toolName) : `${toolLabel(e.toolName)}失败（${e.errorCode}）`,
          description: [formatMs(e.durationMs), e.evidenceIds.length ? `${e.evidenceIds.length} 条证据` : isClarify ? '' : '无证据']
            .filter(Boolean).join(' · '),
          status: e.status === 'ok' ? undefined : 'error',
          detail: (
            <div className="space-y-2">
              {trace && <div><p className="mb-1 text-xs">调用参数</p><JsonBlock value={trace.args} /></div>}
              {e.evidenceIds.length > 0 && (
                <p className="font-mono text-xs break-all">证据：{e.evidenceIds.join('、')}</p>
              )}
            </div>
          ),
        })
        break
      }
      case 'plan_ready':
        rows.push({
          key: `${e.eventIndex}`,
          icon: <BotIcon />,
          title: `主控 Agent 制定计划：${e.plan.mode === 'full' ? '完整尽调' : '单项追问'}`,
          description: `${e.plan.roles.length} 步`,
        })
        break
      case 'role_started':
        if (!finishedRoles.has(e.role)) {
          rows.push({
            key: `${e.eventIndex}`,
            icon: <BotIcon />,
            title: stepTitle(roleStepIndex(events, e.role), roleLabel(e.role, e.name), '执行中'),
            status: live ? 'running' : 'pending',
          })
        }
        break
      case 'role_finished': {
        const failed = e.status === 'failed'
        const degraded = e.status === 'degraded'
        const skipped = e.status === 'skipped'
        const suffix = failed ? '失败' : skipped ? '跳过' : degraded ? '完成（降级）' : '完成'
        rows.push({
          key: `${e.eventIndex}`,
          icon: failed ? <CircleAlertIcon /> : skipped ? <BotIcon /> : <CheckCircle2Icon />,
          title: stepTitle(roleStepIndex(events, e.role), roleLabel(e.role, e.name), suffix),
          description: formatMs(e.durationMs),
          status: failed ? 'error' : undefined,
        })
        break
      }
      case 'verify_finished':
        rows.push({
          key: `${e.eventIndex}`,
          icon: e.status === 'failed' ? <ShieldXIcon /> : <ShieldCheckIcon />,
          title: e.status === 'ok' ? '事实校验通过'
            : e.status === 'retry' ? `事实校验发现 ${e.issues.length} 处问题，带清单重写` : '事实校验未通过，答案未发布',
          status: e.status === 'failed' ? 'error' : undefined,
          detail: e.issues.length ? (
            <ul className="space-y-0.5 text-xs">{e.issues.map((issue, i) => <li key={i}>· {issue}</li>)}</ul>
          ) : undefined,
        })
        break
      case 'run_finished':
        rows.push({
          key: `${e.eventIndex}`,
          icon: e.status === 'failed' || e.status === 'blocked' ? <CircleAlertIcon />
            : e.status === 'succeeded' ? <CheckCircle2Icon /> : <FlagIcon />,
          title: `执行结束：${STATUS_META[e.status].label}`,
          description: [formatMs(e.durationMs), e.errorCode ?? ''].filter(Boolean).join(' · '),
          status: e.status === 'failed' || e.status === 'blocked' ? 'error' : undefined,
        })
        break
    }
  }
  // 执行中且最后一步不是工具执行：模型正在推理。
  // 角色 Agent 执行中已有「第 N 步 · …执行中」行，不再叠一层主控推理提示
  const last = events.at(-1)
  const inRoles = last && ['plan_ready', 'role_started', 'role_finished'].includes(last.type)
    && !events.some((e) => e.type === 'tool_finished' && e.toolName === 'run_dd_agents')
  if (live && last && !inRoles && last.type !== 'run_finished' && last.type !== 'tool_started') {
    const rounds = events.filter((e) => e.type === 'llm_call_finished').length
    rows.push({ key: 'thinking', icon: <BotIcon />, title: `模型推理中（第 ${rounds + 1} 轮）`, status: 'running' })
  }
  return rows
}

export function RunTrace({ events, traces, live }: { events: RunEvent[]; traces: ToolTrace[]; live: boolean }) {
  const rows = buildRows(events, traces, live)
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">{live ? '等待后端事件…' : '没有事件记录'}</p>
  }
  return (
    <Trace aria-live="polite">
      <AnimatePresence initial={false}>
        {rows.map((row) => (
          <motion.div
            key={row.key}
            layout="position"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="min-w-0 max-w-full"
          >
            {row.detail ? (
              <TraceCollapsible>
                <TraceCollapsibleTrigger>
                  <RowLine row={row} />
                </TraceCollapsibleTrigger>
                <TraceCollapsibleContent>{row.detail}</TraceCollapsibleContent>
              </TraceCollapsible>
            ) : (
              <RowLine row={row} />
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </Trace>
  )
}

function RowLine({ row }: { row: Row }) {
  return (
    <TraceLine status={row.status} className="max-w-full">
      <TraceIcon>{row.icon}</TraceIcon>
      <TraceTitle className="truncate">{row.title}</TraceTitle>
      {row.description && <TraceDescription>{row.description}</TraceDescription>}
    </TraceLine>
  )
}
