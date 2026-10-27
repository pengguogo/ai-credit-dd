/**
 * Agent 基座 API 类型 — 与 contracts/agent-api.md 一一对应（契约是唯一来源）。
 * 字段变更先改契约，再改这里。
 */

export type RunStatus =
  | 'running'
  | 'succeeded'
  | 'needs_confirmation'
  | 'needs_clarification'
  | 'blocked'
  | 'insufficient_evidence'
  | 'failed'

export interface Usage {
  promptTokens: number
  completionTokens: number
  totalTokens: number
}

export interface RunOut {
  runId: string
  conversationId: string
  scenarioId: string
  question: string
  status: RunStatus
  answer: string | null
  answerVersion: number | null
  model: string
  usage: Usage
  dataVersion: number
  errorCode: string | null
  errorMessage: string | null
  evidenceIds: string[]
  createdAt: string
}

export interface ToolTrace {
  sequence: number
  toolName: string
  status: 'ok' | 'error'
  args: Record<string, unknown>
  durationMs: number
  errorCode: string | null
}

export interface Timing {
  node: 'compliance' | 'llm' | 'tool' | 'run'
  durationMs: number
  stage?: 'input' | 'output'
  round?: number
  sequence?: number
  toolName?: string
  status?: string
}

export interface ContextSnapshot {
  requestId?: string | null
  historyMessages?: number
  compressedRange?: { fromMessageId: number; toMessageId: number; count: number } | null
  toolSummaryRuns?: string[]
  entities?: Record<string, string[]>
  missingInfo?: string[]
  confirmationReasons?: string[]
  [key: string]: unknown
}

export interface RunDetail extends RunOut {
  toolTraces: ToolTrace[]
  contextSnapshot: ContextSnapshot
  timings: Timing[]
  startedAt: string | null
  finishedAt: string | null
}

export interface Evidence {
  evidenceId: string
  sourceType: 'db_query' | 'document' | 'calculation' | string
  sourceRef: Record<string, unknown>
  snapshot: Record<string, unknown> | unknown[]
  contentHash: string
  dataVersion: number
  createdAt: string
}

export interface AuditEvent {
  id: number
  eventType: string
  actorId: string
  answerVersion: number | null
  payload: Record<string, unknown>
  createdAt: string
}

export interface Confirmation {
  confirmationId: number
  runId: string
  answerVersion: number
  action: 'confirm' | 'reject'
  actorId: string
  createdAt: string
}

export interface Stats {
  totalRuns: number
  statusCounts: Partial<Record<RunStatus, number>>
  blockedByCategory: Record<string, number>
  conclusionRuns: number
  conclusionsWithEvidence: number
  evidenceCount: number
  toolUsage: Record<string, number>
  confirmations: Record<string, number>
  avgDurationMs: number
  p95DurationMs: number
  avgTotalTokens: number
  generatedAt: string
}

/** SSE 事件（契约 §GET /runs/{runId}/events） */
interface EventBase {
  eventIndex: number
  runId: string
}

export type RunEvent =
  | ({ type: 'run_started'; scenarioId: string; question: string; conversationId?: string } & EventBase)
  | ({ type: 'compliance_checked'; stage: 'input' | 'output'; isClean: boolean; durationMs: number } & EventBase)
  | ({ type: 'compliance_blocked'; payload: { stage: string; code: string; category?: string } } & EventBase)
  | ({
      type: 'llm_call_finished'
      round: number
      status: 'ok' | 'error'
      errorCode: string | null
      durationMs: number
      totalTokens?: number
      toolCalls?: string[]
    } & EventBase)
  | ({ type: 'tool_started'; sequence: number; toolName: string } & EventBase)
  | ({
      type: 'tool_finished'
      sequence: number
      toolName: string
      status: 'ok' | 'error'
      durationMs: number
      errorCode: string | null
      evidenceIds: string[]
    } & EventBase)
  | ({
      type: 'run_finished'
      status: RunStatus
      errorCode: string | null
      answerVersion: number | null
      durationMs?: number
    } & EventBase)
  // ---- 尽调多 Agent（契约 §尽调多 Agent，ADR-0008） ----
  | ({
      type: 'plan_ready'
      plan: {
        mode: 'full' | 'followup'
        roles: string[]
        target: { applicationId: string | null; enterpriseId: string }
        focus: string | null
        configFile: string
      }
    } & EventBase)
  | ({ type: 'role_started'; role: string; name: string; parallelGroup: number } & EventBase)
  | ({
      type: 'role_finished'
      role: string
      name: string
      status: RoleStatus
      durationMs: number
      llm: boolean
      evidenceCount: number
      errorCode: string | null
      keyFindings: string[]
    } & EventBase)
  | ({ type: 'verify_finished'; status: 'ok' | 'retry' | 'failed'; attempt: number; issues: string[] } & EventBase)

/** 角色 Agent 的执行状态（role_finished.status） */
export type RoleStatus = 'ok' | 'degraded' | 'skipped' | 'failed'

export interface CatalogColumn {
  key: string
  label: string
}

export type ApprovalStatusFilter = 'pending' | 'pending_review' | 'approved' | 'rejected' | 'open' | ''

export interface Catalog {
  scenarioId: string
  title: string
  note: string
  kind: string
  query: string
  approvalStatus?: string
  total: number
  matched: number
  limit: number
  columns: CatalogColumn[]
  rows: Record<string, string | number | null>[]
  statusCounts?: Partial<Record<'pending' | 'pending_review' | 'approved' | 'rejected', number>>
}

export interface ConversationSummary {
  conversationId: string
  scenarioId: string
  title: string
  updatedAt: string
  turnCount: number
  lastStatus: RunStatus | null
}

export interface ConversationListPage {
  conversations: ConversationSummary[]
  total: number
  limit: number
  offset: number
  hasMore: boolean
}

export interface ConversationMessage {
  id: number
  role: 'user' | 'assistant' | string
  content: string
  runId: string | null
  createdAt: string
}

export interface HealthReady {
  status: 'ok' | 'unavailable'
  checks?: {
    modelLock?: { ok: boolean; model: string }
    database?: { ok: boolean }
    llm?: { ok: boolean; status: string; errorCode: string | null }
  }
  reason?: string
}

/** 会话记忆（契约 §GET/PATCH/DELETE /conversations/{id}/memory，待办 0-6） */
export interface ConversationMemory {
  conversationId: string
  scenarioId: string | null
  entities: Record<string, string[]>
  allowedKeys: string[]
  historyFromMessageId: number | null
  totalMessages: number
  carriedMessages: number
  confirmedConclusions: {
    runId: string
    answerVersion: number
    answer: string
    confirmedBy: string
    confirmedAt: string
  }[]
  version: number
  updatedBy: string | null
  updatedAt: string | null
  events: {
    id: number
    eventType: 'memory_corrected' | 'memory_cleared' | string
    actorId: string
    payload: Record<string, unknown>
    createdAt: string
  }[]
}

export type MemoryClearScope = 'entities' | 'history' | 'all'

/** 尽调单步核对 POST /api/agent/dd/steps */
export interface DdStepToolResult {
  toolName: string
  status: 'ok' | 'error' | 'skipped'
  errorCode: string | null
  message: string | null
  data: unknown
}

export interface DdStepResult {
  step: string
  label: string
  status: 'ok' | 'partial' | 'error'
  enterpriseId: string | null
  applicationId: string | null
  tools: DdStepToolResult[]
  note: string
}

/** 报告建档：报告本身没有状态，审核结论记在贷款申请上。 */
export interface WorkspaceAsset {
  applyAmount: number | null
  reportGeneratedAt: string
  id: string
  scenarioId: string
  applicationId: string | null
  enterpriseId: string | null
  enterpriseName: string | null
  conversationId: string | null
  runId: string
  kind: string
  title: string
  summary: string | null
  evidenceCount: number
  contentSha256: string | null
  createdBy: string
  createdAt: string
  updatedAt: string
}

export type WorkspaceAssetDetail = WorkspaceAsset

export interface WorkspaceAssetList {
  assets: WorkspaceAsset[]
  total: number
  limit: number
  offset: number
  hasMore: boolean
}
