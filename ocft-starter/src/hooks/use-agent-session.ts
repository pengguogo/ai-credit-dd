/**
 * 一个对话会话：提问 → 异步 run → 实时事件 → 结束后取详情 / 证据 / 审计 → 业务确认。
 * 所有状态都来自后端真实返回；失败如实记录错误码，不生成任何替代答案。
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, api, streamRunEvents } from '@/lib/api'
import { newIdempotencyKey } from '@/lib/format'
import type { AuditEvent, ConversationMessage, Evidence, RunDetail, RunEvent, RunStatus } from '@/lib/types'

export interface TurnError {
  code: string
  message: string
}

export interface Turn {
  id: string
  question: string
  /** 本轮随问题发送的图片（只在前端内存，后端不落库） */
  images: string[]
  runId: string | null
  status: RunStatus
  events: RunEvent[]
  detail: RunDetail | null
  evidence: Evidence[] | null
  audit: AuditEvent[] | null
  error: TurnError | null
  startedAt: number
  /** 本轮是现场发起的：结束后前端渐进吐字；打开历史为 false。 */
  revealAnswer: boolean
}

export interface ConfirmResult {
  ok: boolean
  message: string
}

function toTurnError(exc: unknown): TurnError {
  if (exc instanceof ApiError) return { code: exc.errorCode, message: exc.message }
  return { code: 'client_error', message: String(exc) }
}

export function useAgentSession(actorId: string, scenarioId: string) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const abortRef = useRef<AbortController>(new AbortController())

  // @why 挂载时新建控制器：StrictMode 开发模式会先卸载再挂载，卸载时 abort 过的控制器不能复用
  useEffect(() => {
    abortRef.current = new AbortController()
    return () => abortRef.current.abort()
  }, [])

  const patch = useCallback((id: string, update: Partial<Turn> | ((t: Turn) => Partial<Turn>)) => {
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...(typeof update === 'function' ? update(t) : update) } : t)))
  }, [])

  const loadResult = useCallback(async (id: string, runId: string) => {
    const [detail, evidence, audit] = await Promise.all([
      api.getRun(actorId, runId),
      api.getEvidence(actorId, runId),
      api.getAudit(actorId, runId),
    ])
    patch(id, { detail, evidence, audit, status: detail.status })
  }, [actorId, patch])

  const ask = useCallback(async (raw: string, images: string[] = []) => {
    const question = raw.trim()
    if (!question || busy) return
    const id = crypto.randomUUID()
    const signal = abortRef.current.signal
    setTurns((all) => [...all, {
      id, question, images, runId: null, status: 'running', events: [], detail: null,
      evidence: null, audit: null, error: null, startedAt: Date.now(), revealAnswer: true,
    }])
    setBusy(true)
    try {
      const started = await api.startRun(actorId, question, conversationId, scenarioId, images)
      if (signal.aborted) return
      setConversationId(started.conversationId)
      patch(id, { runId: started.runId })
      await streamRunEvents(actorId, started.runId, (event) => {
        patch(id, (t) => ({
          events: [...t.events, event],
          ...(event.type === 'run_finished' ? { status: event.status } : {}),
        }))
      }, signal)
      if (signal.aborted) return
      await loadResult(id, started.runId)
    } catch (exc) {
      if (!signal.aborted) patch(id, { status: 'failed', error: toTurnError(exc) })
    } finally {
      if (!signal.aborted) setBusy(false)
    }
  }, [actorId, busy, conversationId, loadResult, patch, scenarioId])

  const confirm = useCallback(async (turn: Turn, action: 'confirm' | 'reject', comment: string): Promise<ConfirmResult> => {
    const version = turn.detail?.answerVersion
    if (!turn.runId || version == null) return { ok: false, message: '该结果没有可确认的结论版本' }
    try {
      await api.confirm(actorId, turn.runId, {
        answerVersion: version, action, comment: comment || undefined,
        idempotencyKey: newIdempotencyKey(),
      })
      patch(turn.id, { audit: await api.getAudit(actorId, turn.runId) })
      return { ok: true, message: action === 'confirm' ? '已确认，审计已留痕' : '已驳回，审计已留痕' }
    } catch (exc) {
      const err = toTurnError(exc)
      return { ok: false, message: `${err.message}（${err.code}）` }
    }
  }, [actorId, patch])

  const reset = useCallback(() => {
    abortRef.current.abort()
    abortRef.current = new AbortController()
    setTurns([])
    setConversationId(null)
    setBusy(false)
  }, [])

  const open = useCallback(async (nextId: string): Promise<string | null> => {
    abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setBusy(true)
    setConversationId(nextId)
    setTurns([])
    try {
      const messages = await api.messages(actorId, nextId)
      if (controller.signal.aborted) return '已取消'
      const built = await buildTurns(actorId, messages, controller.signal)
      if (controller.signal.aborted) return '已取消'
      setTurns(built)
      return null
    } catch (exc) {
      if (controller.signal.aborted) return '已取消'
      setConversationId(null)
      setTurns([])
      return toTurnError(exc).message
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }, [actorId])

  return { turns, conversationId, busy, ask, confirm, reset, open }
}

async function buildTurns(actorId: string, messages: ConversationMessage[], signal: AbortSignal): Promise<Turn[]> {
  const pairs: { question: string; runId: string | null; createdAt: string }[] = []
  let pending: ConversationMessage | null = null
  for (const message of messages) {
    if (message.role === 'user') {
      if (pending) pairs.push({ question: pending.content, runId: pending.runId, createdAt: pending.createdAt })
      pending = message
      continue
    }
    if (message.role !== 'assistant') continue
    pairs.push({
      question: pending?.content ?? '',
      runId: message.runId ?? pending?.runId ?? null,
      createdAt: pending?.createdAt ?? message.createdAt,
    })
    pending = null
  }
  if (pending) pairs.push({ question: pending.content, runId: pending.runId, createdAt: pending.createdAt })

  return Promise.all(pairs.map(async (pair, index) => {
    const base: Turn = {
      id: pair.runId ?? `history-${index}`,
      question: pair.question,
      images: [],
      runId: pair.runId,
      status: 'failed',
      events: [],
      detail: null,
      evidence: null,
      audit: null,
      error: pair.runId ? null : { code: 'missing_run', message: '这条消息没有对应的执行记录' },
      startedAt: Date.parse(pair.createdAt) || Date.now(),
      revealAnswer: false,
    }
    if (!pair.runId || signal.aborted) return base
    const [detail, evidence, audit, events] = await Promise.all([
      api.getRun(actorId, pair.runId),
      api.getEvidence(actorId, pair.runId),
      api.getAudit(actorId, pair.runId),
      collectEvents(actorId, pair.runId, signal),
    ])
    return { ...base, status: detail.status, detail, evidence, audit, events, error: null }
  }))
}

async function collectEvents(actorId: string, runId: string, signal: AbortSignal): Promise<RunEvent[]> {
  const events: RunEvent[] = []
  try {
    await streamRunEvents(actorId, runId, (event) => events.push(event), signal)
  } catch {
    // 轨迹拉不齐时仍展示已保存的结论，不把整段历史判失败
  }
  return events
}
