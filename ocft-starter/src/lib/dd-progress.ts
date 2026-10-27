import type { RunEvent, RunStatus } from './types'

const STAGES = [
  ['control', '主控'],
  ['business', '工商'],
  ['finance', '财报'],
  ['opinion', '舆情'],
  ['fraud', '反欺诈'],
  ['rating', '评级授信'],
  ['report', '生成报告'],
] as const

type StageState = 'waiting' | 'running' | 'ok' | 'degraded' | 'skipped' | 'failed'

/** 只使用本轮真实事件；重试以最后一次节点状态为准。 */
export function diligenceProgress(events: RunEvent[], status: RunStatus, answer?: string | null) {
  const states = new Map<string, StageState>()
  for (const event of events) {
    if (event.type === 'run_started') states.set('control', status === 'running' ? 'running' : 'failed')
    if (event.type === 'plan_ready') states.set('control', 'ok')
    if (event.type === 'role_started') states.set(event.role, status === 'running' ? 'running' : 'failed')
    if (event.type === 'role_finished') states.set(event.role, event.status)
  }
  const outputReady = (status === 'succeeded' || status === 'needs_confirmation') && Boolean(answer?.trim())
  // 报告 Agent 完成后仍需等待实际输出，二者只计一个节点。
  if (states.get('report') === 'ok' && !outputReady) {
    states.set('report', status === 'running' ? 'running' : status === 'succeeded' || status === 'needs_confirmation' ? 'waiting' : 'failed')
  }
  const stages = STAGES.map(([id, label]) => ({ id, label, state: states.get(id) ?? 'waiting' }))
  return { stages, completed: stages.filter(stage => stage.state === 'ok').length }
}
