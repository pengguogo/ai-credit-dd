/** 审计时间线 + 业务确认 / 驳回（契约 §confirmations：幂等、绑定结论版本、同事务留痕）。 */
import { CheckIcon, XIcon } from 'lucide-react'
import { useId, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import type { ConfirmResult, Turn } from '@/hooks/use-agent-session'
import { auditLabel, formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const CONFIRMABLE = new Set(['succeeded', 'needs_confirmation'])

function payloadSummary(eventType: string, payload: Record<string, unknown>): string {
  if (eventType === 'run_finished') return `状态 ${String(payload.status)}${payload.errorCode ? ` · ${String(payload.errorCode)}` : ''}`
  if (eventType === 'compliance_blocked') return `${String(payload.stage)} · ${String(payload.code)}`
  if (eventType === 'pii_redacted') return `${String(payload.stage)} · ${Object.keys((payload.counts as object) ?? {}).join('、')}`
  if (eventType.startsWith('confirmation_')) return payload.comment ? `意见：${String(payload.comment)}` : '无意见'
  if (eventType === 'run_started') return payload.requestId ? `请求 ${String(payload.requestId)}` : ''
  return ''
}

export function AuditPanel({ turn, onConfirm, allowConfirm = true }: {
  turn: Turn
  onConfirm: (turn: Turn, action: 'confirm' | 'reject', comment: string) => Promise<ConfirmResult>
  /** 无 confirm 权限时只展示审计，不展示确认/驳回 */
  allowConfirm?: boolean
}) {
  const [comment, setComment] = useState('')
  const [pending, setPending] = useState<'confirm' | 'reject' | null>(null)
  const [result, setResult] = useState<ConfirmResult | null>(null)
  const commentId = useId()
  const audit = turn.audit
  const decided = audit?.find((e) => e.eventType.startsWith('confirmation_'))
  const canConfirm = allowConfirm
    && CONFIRMABLE.has(turn.status)
    && turn.detail?.answerVersion != null
    && !decided

  async function submit(action: 'confirm' | 'reject') {
    setPending(action)
    const r = await onConfirm(turn, action, comment.trim())
    setResult(r)
    setPending(null)
    if (r.ok) setComment('')
  }

  return (
    <div className="space-y-4">
      {canConfirm && (
        <section aria-labelledby={`${commentId}-title`} className="space-y-2 rounded-lg border border-brand/30 bg-brand-soft/60 p-3">
          <h3 id={`${commentId}-title`} className="text-sm font-medium">
            业务确认（结论版本 v{turn.detail?.answerVersion}）
          </h3>
          {(turn.detail?.contextSnapshot.confirmationReasons ?? []).map((r) => (
            <p key={r} className="text-xs text-muted-foreground">{r}</p>
          ))}
          <label htmlFor={commentId} className="sr-only">确认意见</label>
          <Textarea
            id={commentId}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="确认意见（可选），如：同意，按规则引擎结论处理"
            maxLength={500}
            className="min-h-16 bg-card"
          />
          <div className="flex gap-2">
            <Button onClick={() => submit('confirm')} disabled={pending !== null}>
              {pending === 'confirm' ? <Spinner /> : <CheckIcon />}确认结论
            </Button>
            <Button variant="outline" onClick={() => submit('reject')} disabled={pending !== null}>
              {pending === 'reject' ? <Spinner /> : <XIcon />}驳回
            </Button>
          </div>
        </section>
      )}
      <p role="status" className={cn('text-sm', result ? (result.ok ? 'text-success' : 'text-destructive') : 'sr-only')}>
        {result?.message ?? ''}
      </p>
      {!CONFIRMABLE.has(turn.status) && turn.status !== 'running' && (
        <p className="text-xs text-muted-foreground">该状态没有可确认的结论，只记录审计。</p>
      )}
      {allowConfirm === false && CONFIRMABLE.has(turn.status) && !decided && (
        <p className="text-xs text-muted-foreground">当前角色为只读，不能确认或驳回结论。</p>
      )}
      {audit === null ? (
        <p className="text-sm text-muted-foreground">执行结束后加载审计记录…</p>
      ) : (
        <ol className="relative space-y-3 border-l pl-4">
          {audit.map((e) => (
            <li key={e.id} className="relative">
              <span
                aria-hidden
                className={cn(
                  'absolute top-1.5 -left-[21px] size-2.5 rounded-full border-2 border-card',
                  e.eventType === 'compliance_blocked' || e.eventType === 'confirmation_rejected' ? 'bg-destructive'
                    : e.eventType === 'confirmation_created' ? 'bg-success' : 'bg-muted-foreground/50',
                )}
              />
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-sm font-medium">{auditLabel(e.eventType)}</span>
                <span className="font-mono text-xs text-muted-foreground">{formatTime(e.createdAt)} · {e.actorId}</span>
                {e.answerVersion != null && <span className="text-xs text-muted-foreground">v{e.answerVersion}</span>}
              </div>
              <p className="text-xs break-all text-muted-foreground">{payloadSummary(e.eventType, e.payload)}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
