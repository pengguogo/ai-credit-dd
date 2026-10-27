/**
 * Agent 基座 API 客户端。业务数据只来自这里（AGENTS.md 前端约定）。
 * 身份：登录后带 Authorization Bearer；并回写 X-Actor-Id = username（兼容旧接口）。
 */
import { readSession, type AuthUser } from './auth'
import type { CatalogKind } from './catalog-tables'
import type {
  ApprovalStatusFilter,
  AuditEvent,
  Confirmation,
  DdStepResult,
  Evidence,
  HealthReady,
  RunDetail,
  RunEvent,
  RunOut,
  Stats,
  Catalog,
  ConversationListPage,
  ConversationMemory,
  ConversationMessage,
  MemoryClearScope,
  WorkspaceAssetDetail,
  WorkspaceAssetList,
} from './types'

const BASE = '/api'

export type CsvImportReport = {
  importId: string
  status: 'imported' | 'rejected'
  added: number
  skipped: number
  files: { fileName: string; added: number; skipped: number }[]
  errors: {
    fileName: string
    row: number | null
    field: string
    errorCode: string
    message: string
  }[]
}

export class CsvImportError extends Error {
  constructor(readonly report: CsvImportReport) {
    super('CSV校验未通过，本次未写入数据')
    this.name = 'CsvImportError'
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly errorCode: string

  constructor(status: number, errorCode: string, message: string) {
    super(message)
    this.status = status
    this.errorCode = errorCode
  }
}

function authHeaders(actorId: string | null, init?: HeadersInit): Headers {
  const headers = new Headers(init)
  const session = readSession()
  const actor = session?.user.username || actorId
  if (actor) headers.set('X-Actor-Id', actor)
  if (session?.token) headers.set('Authorization', `Bearer ${session.token}`)
  return headers
}

async function request<T>(path: string, actorId: string | null, init: RequestInit = {}): Promise<T> {
  const headers = authHeaders(actorId, init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers })
  } catch (exc) {
    throw new ApiError(0, 'network_error', `无法连接后端：${String(exc)}`)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new ApiError(res.status, body.errorCode ?? `http_${res.status}`,
      body.message ?? body.reason ?? `请求失败（HTTP ${res.status}）`)
  }
  return body as T
}

export type SysRole = {
  id: number
  code: string
  name: string
  description: string
  permissions: string[]
  createdAt: string | null
}

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; expiresInSeconds: number; user: AuthUser }>('/auth/login', null, {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  logout: () =>
    request<{ ok: boolean }>('/auth/logout', null, { method: 'POST' }),

  me: () =>
    request<{ user: AuthUser }>('/auth/me', null),

  adminRoles: () =>
    request<{ roles: SysRole[] }>('/admin/roles', null),

  createRole: (body: { code: string; name: string; description?: string; permissions: string[] }) =>
    request<SysRole>('/admin/roles', null, { method: 'POST', body: JSON.stringify(body) }),

  adminUsers: () =>
    request<{ users: AuthUser[] }>('/admin/users', null),

  createUser: (body: { username: string; displayName?: string; password: string; roleCode: string }) =>
    request<AuthUser>('/admin/users', null, { method: 'POST', body: JSON.stringify(body) }),

  patchUser: (userId: number, body: {
    displayName?: string
    roleCode?: string
    status?: string
    password?: string
  }) =>
    request<AuthUser>(`/admin/users/${userId}`, null, { method: 'PATCH', body: JSON.stringify(body) }),

  /** 仅新增；重复相同行跳过，422通过CsvImportError.report返回逐行错误。 */
  importCsvFiles: async (actorId: string, files: File[]): Promise<CsvImportReport> => {
    if (!files.length || files.length > 9) {
      throw new ApiError(400, 'invalid_files', '请选择1—9个业务CSV文件')
    }
    const body = {
      files: await Promise.all(files.map(async (file) => ({
        fileName: file.name,
        content: await file.text(),
      }))),
    }
    let response: Response
    try {
      response = await fetch(`${BASE}/agent/data/imports`, {
        method: 'POST',
        headers: authHeaders(actorId, { 'Content-Type': 'application/json' }),
        body: JSON.stringify(body),
      })
    } catch {
      throw new ApiError(0, 'network_error', '无法连接导入接口，请核对后端服务')
    }
    const result = await response.json().catch(() => ({}))
    if (response.status === 422 && result.status === 'rejected') {
      throw new CsvImportError(result as CsvImportReport)
    }
    if (!response.ok) {
      throw new ApiError(response.status, result.errorCode ?? `http_${response.status}`,
        result.message ?? 'CSV导入失败，请检查请求格式')
    }
    return result as CsvImportReport
  },

  health: async (): Promise<HealthReady> => {
    try {
      const res = await fetch(`${BASE}/health/ready`)
      return (await res.json()) as HealthReady
    } catch {
      return { status: 'unavailable', reason: '后端未连接' }
    }
  },

  /** attachments：图片 data URL / http(s) URL（契约 §多模态输入约定，≤4 张） */
  startRun: (actorId: string, question: string, conversationId: string | null, scenarioId: string, images: string[] = []) =>
    request<RunOut>('/agent/runs', actorId, {
      method: 'POST',
      body: JSON.stringify({
        question,
        scenarioId,
        mode: 'async',
        ...(conversationId ? { conversationId } : {}),
        ...(images.length ? { attachments: images.map((imageUrl) => ({ type: 'image_url', imageUrl })) } : {}),
      }),
    }),

  getRun: (actorId: string, runId: string) =>
    request<RunDetail>(`/agent/runs/${encodeURIComponent(runId)}`, actorId),

  getEvidence: (actorId: string, runId: string) =>
    request<{ evidence: Evidence[] }>(`/agent/runs/${encodeURIComponent(runId)}/evidence`, actorId)
      .then((r) => r.evidence),

  getAudit: (actorId: string, runId: string) =>
    request<{ events: AuditEvent[] }>(`/agent/runs/${encodeURIComponent(runId)}/audit`, actorId)
      .then((r) => r.events),

  confirm: (actorId: string, runId: string, body: {
    answerVersion: number
    action: 'confirm' | 'reject'
    comment?: string
    idempotencyKey: string
  }) =>
    request<Confirmation>(`/agent/runs/${encodeURIComponent(runId)}/confirmations`, actorId, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  stats: (actorId: string) => request<Stats>('/agent/stats', actorId),

  /** 报告列表：按企业 / 申请 / 关键词检索（报告本身没有状态） */
  assets: (actorId: string, opts: {
    keyword?: string
    applicationId?: string
    enterpriseId?: string
    limit?: number
    offset?: number
  } = {}) => {
    const params = new URLSearchParams()
    if (opts.keyword?.trim()) params.set('keyword', opts.keyword.trim())
    if (opts.applicationId) params.set('applicationId', opts.applicationId)
    if (opts.enterpriseId) params.set('enterpriseId', opts.enterpriseId)
    if (opts.limit != null) params.set('limit', String(opts.limit))
    if (opts.offset != null) params.set('offset', String(opts.offset))
    const qs = params.toString()
    return request<WorkspaceAssetList>(`/agent/assets${qs ? `?${qs}` : ''}`, actorId)
  },

  asset: (actorId: string, assetId: string) =>
    request<WorkspaceAssetDetail>(`/agent/assets/${encodeURIComponent(assetId)}`, actorId),

  catalog: (
    actorId: string,
    scenarioId: string,
    q = '',
    kind: CatalogKind = 'applications',
    approvalStatus: ApprovalStatusFilter = '',
  ) => {
    const params = new URLSearchParams()
    params.set('kind', kind)
    if (q.trim()) params.set('q', q.trim())
    if (approvalStatus) params.set('approvalStatus', approvalStatus)
    return request<Catalog>(`/agent/catalog/${encodeURIComponent(scenarioId)}?${params}`, actorId)
  },

  createCatalogRecord: (actorId: string, scenarioId: string, kind: CatalogKind, body: Record<string, unknown>) =>
    request<{ id: number; kind: string; row: Record<string, string | number | null> }>(
      `/agent/catalog/${encodeURIComponent(scenarioId)}/${encodeURIComponent(kind)}/records`,
      actorId,
      { method: 'POST', body: JSON.stringify(body) },
    ),

  updateCatalogRecord: (actorId: string, scenarioId: string, kind: CatalogKind, id: number, body: Record<string, unknown>) =>
    request<{ id: number; kind: string; row: Record<string, string | number | null> }>(
      `/agent/catalog/${encodeURIComponent(scenarioId)}/${encodeURIComponent(kind)}/records/${id}`,
      actorId,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),

  deleteCatalogRecord: (actorId: string, scenarioId: string, kind: CatalogKind, id: number) =>
    request<{ id: number; kind: string; deleted: boolean }>(
      `/agent/catalog/${encodeURIComponent(scenarioId)}/${encodeURIComponent(kind)}/records/${id}`,
      actorId,
      { method: 'DELETE' },
    ),

  /** 人工审核贷款申请：通过 / 拒绝 + 必填原因，服务端记录审核人与时间 */
  reviewApplication: (actorId: string, scenarioId: string, id: number, body: {
    decision: 'approved' | 'rejected'
    reason: string
  }) =>
    request<{ id: number; kind: string; row: Record<string, string | number | null> }>(
      `/agent/catalog/${encodeURIComponent(scenarioId)}/applications/records/${id}/review`,
      actorId,
      { method: 'POST', body: JSON.stringify(body) },
    ),


  /** 单步尽调核对：按维度直接跑当前步骤工具（含报告汇总导出） */
  ddStep: (actorId: string, body: {
    step: 'business' | 'finance' | 'opinion' | 'fraud' | 'credit-risk' | 'report'
    enterpriseId?: string
    applicationId?: string
  }) =>
    request<DdStepResult>('/agent/dd/steps', actorId, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  conversations: (actorId: string, opts: {
    q?: string
    limit?: number
    offset?: number
    scenarioId?: string
  } = {}) => {
    const params = new URLSearchParams()
    if (opts.q?.trim()) params.set('q', opts.q.trim())
    if (opts.limit != null) params.set('limit', String(opts.limit))
    if (opts.offset != null) params.set('offset', String(opts.offset))
    if (opts.scenarioId) params.set('scenarioId', opts.scenarioId)
    const qs = params.toString()
    return request<ConversationListPage>(
      `/agent/conversations${qs ? `?${qs}` : ''}`,
      actorId,
    )
  },

  messages: (actorId: string, conversationId: string) =>
    request<{ messages: ConversationMessage[] }>(
      `/agent/conversations/${encodeURIComponent(conversationId)}/messages`, actorId)
      .then((body) => body.messages),

  memory: (actorId: string, conversationId: string) =>
    request<ConversationMemory>(`/agent/conversations/${encodeURIComponent(conversationId)}/memory`, actorId),

  /** 只改出现的键；空数组表示删除该键。expectedVersion 不一致时返回 409 */
  correctMemory: (actorId: string, conversationId: string, entities: Record<string, string[]>, expectedVersion: number) =>
    request<ConversationMemory>(`/agent/conversations/${encodeURIComponent(conversationId)}/memory`, actorId, {
      method: 'PATCH',
      body: JSON.stringify({ entities, expectedVersion }),
    }),

  clearMemory: (actorId: string, conversationId: string, scope: MemoryClearScope, expectedVersion: number) =>
    request<ConversationMemory>(
      `/agent/conversations/${encodeURIComponent(conversationId)}/memory?scope=${scope}&expectedVersion=${expectedVersion}`,
      actorId, { method: 'DELETE' }),
}

/**
 * 订阅 run 事件流。原生 EventSource 不能带 X-Actor-Id，这里用 fetch 读流并解析 SSE。
 * 断线时带 Last-Event-ID 重连，直到收到 run_finished 或被取消。
 */
export async function streamRunEvents(
  actorId: string,
  runId: string,
  onEvent: (event: RunEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  let lastId = 0
  let finished = false
  for (let attempt = 0; !finished && attempt < 5 && !signal.aborted; attempt += 1) {
    try {
      const res = await fetch(`${BASE}/agent/runs/${encodeURIComponent(runId)}/events`, {
        headers: { 'X-Actor-Id': actorId, ...(lastId ? { 'Last-Event-ID': String(lastId) } : {}) },
        signal,
      })
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => ({}))
        throw new ApiError(res.status, body.errorCode ?? `http_${res.status}`, body.message ?? '事件流不可用')
      }
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
      let buffer = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += value
        let cut = buffer.indexOf('\n\n')
        while (cut !== -1) {
          const event = parseBlock(buffer.slice(0, cut))
          buffer = buffer.slice(cut + 2)
          if (event) {
            lastId = event.eventIndex
            onEvent(event)
            if (event.type === 'run_finished') finished = true
          }
          cut = buffer.indexOf('\n\n')
        }
      }
    } catch (exc) {
      if (signal.aborted) return
      if (exc instanceof ApiError && exc.status >= 400 && exc.status < 500) throw exc
      await new Promise((r) => setTimeout(r, 500 * (attempt + 1)))
    }
  }
  if (!finished && !signal.aborted) {
    throw new ApiError(0, 'stream_interrupted', '事件流中断，已停止重连')
  }
}

function parseBlock(block: string): RunEvent | null {
  let type = ''
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue // 心跳注释
    if (line.startsWith('event: ')) type = line.slice(7).trim()
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  if (!type || !data) return null
  return { type, ...JSON.parse(data) } as RunEvent
}
