import type { AuditEvent, RunEvent, RunStatus } from './types'

/** 并行取证三步（工商 / 财报 / 舆情）是否都已结束。 */
export function parallelProbeDone(events: RunEvent[]): boolean {
  if (!Array.isArray(events)) return false
  const plan = events.find((e) => e?.type === 'plan_ready')
  if (!plan || plan.type !== 'plan_ready') return false
  const roles = plan.plan?.roles
  if (!Array.isArray(roles)) return false
  const finished = new Set(
    events.filter((e) => e?.type === 'role_finished').map((e) => e.role),
  )
  const planned = new Set(roles)
  return (['business', 'finance', 'opinion'] as const).every(
    (role) => !planned.has(role) || finished.has(role),
  )
}

export interface StatusMeta {
  label: string
  /** 给用户的下一步提示（诚实说明，不粉饰） */
  hint: string
  tone: 'brand' | 'success' | 'warning' | 'info' | 'danger' | 'muted'
}

export const STATUS_META: Record<RunStatus, StatusMeta> = {
  running: { label: '执行中', hint: 'Agent 正在调用工具取证', tone: 'info' },
  succeeded: { label: '已完成', hint: '结论均有证据支撑', tone: 'success' },
  needs_confirmation: { label: '待业务确认', hint: '高风险结论，需业务人员确认或驳回后生效', tone: 'brand' },
  needs_clarification: { label: '需要补充信息', hint: '信息不足以继续，请回答 Agent 的问题', tone: 'warning' },
  insufficient_evidence: { label: '证据不足', hint: '没有取得可支撑结论的数据，未给出结论', tone: 'warning' },
  blocked: { label: '合规拦截', hint: '请求或回答触发合规规则，已拦截并留痕', tone: 'danger' },
  failed: { label: '执行失败', hint: '执行未完成，以下为真实错误信息', tone: 'danger' },
}

export type ConfirmationState = 'pending' | 'confirmed' | 'rejected'

export interface ConfirmationStatus {
  state: ConfirmationState
  label: string
  event: AuditEvent | null
}

/** 只取追加式审计中的最新确认事件；没有确认事件时保持待确认。 */
export function confirmationStatus(events: AuditEvent[] | null | undefined): ConfirmationStatus {
  const event = [...(events ?? [])].reverse().find((item) =>
    item.eventType === 'confirmation_created' || item.eventType === 'confirmation_rejected',
  ) ?? null
  if (event?.eventType === 'confirmation_created') return { state: 'confirmed', label: '已确认', event }
  if (event?.eventType === 'confirmation_rejected') return { state: 'rejected', label: '已驳回', event }
  return { state: 'pending', label: '待确认', event: null }
}

export const TONE_CLASS: Record<StatusMeta['tone'], string> = {
  brand: 'bg-brand-soft text-accent-foreground',
  success: 'bg-success/10 text-success',
  warning: 'bg-warning/10 text-warning',
  info: 'bg-info/10 text-info',
  danger: 'bg-destructive/10 text-destructive',
  muted: 'bg-muted text-muted-foreground',
}

/** 工具名 → 中文动作描述（Trace 标题用，写成完整句子便于读屏） */
const TOOL_LABELS: Record<string, string> = {
  search_credit_applications: '检索信贷申请',
  get_credit_application: '读取申请详情',
  run_credit_rules: '执行 R001–R005 审批规则',
  sql_query: '只读统计查询',
  request_clarification: '向用户请求澄清',
  get_loan_application: '读取贷款申请',
  find_enterprise: '定位企业',
  verify_business_info: '工商核验',
  analyze_financials: '财报解析',
  scan_public_opinion: '舆情扫描',
  detect_fraud_signals: '反欺诈检测',
  rate_risk: '风险评级',
  calc_credit_limit: '额度测算',
  build_dd_report: '生成尽调报告',
  run_dd_agents: '调度尽调角色 Agent',
}

/** 尽调六个角色 Agent，顺序与后端 ROLE_ORDER 一致（scenarios/dd04/agents.yaml） */
export const DD_ROLES: { role: string; name: string; duty: string }[] = [
  { role: 'business', name: '工商核验', duty: '经营状态、股权控制、关联与担保' },
  { role: 'finance', name: '财报解析', duty: '三年科目、偿债盈利营运指标、勾稽' },
  { role: 'opinion', name: '舆情扫描', duty: '舆情事件、涉诉、风险标签与评分' },
  { role: 'fraud', name: '反欺诈', duty: '现金流背离、应收存货异常、担保圈' },
  { role: 'rating', name: '评级授信', duty: '评分卡评级、额度测算、风控条件' },
  { role: 'report', name: '报告', duty: '五部分结构化尽调报告' },
]

export const ROLE_STATUS_META: Record<'waiting' | 'running' | 'ok' | 'degraded' | 'skipped' | 'failed', {
  label: string
  tone: StatusMeta['tone']
}> = {
  waiting: { label: '等待上游', tone: 'muted' },
  running: { label: '执行中', tone: 'info' },
  ok: { label: '完成', tone: 'success' },
  degraded: { label: '降级·需复核', tone: 'warning' },
  skipped: { label: '本次不需要', tone: 'muted' },
  failed: { label: '失败', tone: 'danger' },
}

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name
}

const CATEGORY_LABELS: Record<string, string> = {
  politics: '政治敏感',
  porn: '色情低俗',
  abuse: '辱骂攻击',
  crime: '违法犯罪',
  privacy: '他人隐私',
  prompt_injection: '提示词注入',
  label_probe: '套取内部数据',
  financial_promise: '收益承诺',
  label_leak: '内部数据泄漏',
  unverified_regulation: '法规引述无法核验',
  other: '其他',
}

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category
}

const AUDIT_LABELS: Record<string, string> = {
  run_started: '开始执行',
  run_finished: '执行结束',
  compliance_blocked: '合规拦截',
  pii_redacted: '个人信息已掩码',
  confirmation_created: '业务确认',
  confirmation_rejected: '业务驳回',
}

export function auditLabel(eventType: string): string {
  return AUDIT_LABELS[eventType] ?? eventType
}

export function formatMs(ms: number | undefined | null): string {
  if (ms == null) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString('zh-CN', { hour12: false })
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID().replaceAll('-', '')
}
