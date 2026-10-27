/**
 * 贷款申请人工审核弹窗：选择「审核通过 / 审核拒绝」并填写原因（必填）。
 * 审核结论、原因、审核人与时间由后端同一事务写入；成功后刷新列表。
 */
import { CheckIcon, XIcon } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import { createPortal } from 'react-dom'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { SCENARIO_ID } from '@/data/scenario'
import { ApiError, api } from '@/lib/api'
import { cn } from '@/lib/utils'

export type ReviewDecision = 'approved' | 'rejected'

/** 列表行里审核需要的字段（其余字段不参与提交）。 */
export interface ReviewTarget {
  id: number
  applicationId: string
  status: string
}

const REASON_LIMIT = 500

const DECISIONS: { value: ReviewDecision; label: string; hint: string }[] = [
  { value: 'approved', label: '审核通过', hint: '同意本次贷款申请' },
  { value: 'rejected', label: '审核拒绝', hint: '不同意本次贷款申请' },
]

export function ReviewDialog({ actorId, target, open, onClose, onReviewed }: {
  actorId: string
  target: ReviewTarget | null
  open: boolean
  onClose: () => void
  /** 审核成功后父级刷新列表 */
  onReviewed: () => void
}) {
  const titleId = useId()
  // 不预选结论：审核是业务决策，必须由审核人明确选择通过或拒绝
  const [decision, setDecision] = useState<ReviewDecision | null>(null)
  const [reason, setReason] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, pending, onClose])

  if (!open || !target) return null

  const submit = async () => {
    const text = reason.trim()
    if (!decision) {
      setError('请选择审核结论：审核通过或审核拒绝')
      return
    }
    if (!text) {
      setError('请填写审核原因（通过或拒绝都必须说明理由）')
      return
    }
    setPending(true)
    setError('')
    try {
      await api.reviewApplication(actorId, SCENARIO_ID, target.id, { decision, reason: text })
      onReviewed()
      onClose()
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '审核失败')
    } finally {
      setPending(false)
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 py-10"
      onMouseDown={() => { if (!pending) onClose() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="surface-panel-solid flex max-h-[min(38rem,calc(100vh-5rem))] w-full max-w-lg flex-col overflow-hidden rounded-xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="border-b px-4 py-3">
          <h2 id={titleId} className="text-base font-medium">审核贷款申请 {target.applicationId}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            请选择审核结论并填写原因；结论与原因会记入审批留痕，提交后不可在本窗口撤回。
          </p>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          <div role="radiogroup" aria-label="审核结论" className="grid grid-cols-2 gap-2">
            {DECISIONS.map((item) => {
              const active = decision === item.value
              return (
                <button
                  key={item.value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  disabled={pending}
                  onClick={() => setDecision(item.value)}
                  className={cn(
                    'flex cursor-pointer flex-col items-start gap-0.5 rounded-lg border px-3 py-2 text-left transition-colors',
                    active
                      ? item.value === 'approved'
                        ? 'border-success/60 bg-success/10 text-success'
                        : 'border-destructive/60 bg-destructive/10 text-destructive'
                      : 'border-border bg-card hover:bg-muted/60',
                  )}
                >
                  <span className="flex items-center gap-1.5 text-sm font-medium">
                    {item.value === 'approved' ? <CheckIcon className="size-4" /> : <XIcon className="size-4" />}
                    {item.label}
                  </span>
                  <span className="text-[11px] text-muted-foreground">{item.hint}</span>
                </button>
              )
            })}
          </div>

          <label className="block text-xs">
            <span className="text-muted-foreground">
              审核原因 <span className="text-destructive">*</span>
            </span>
            <Textarea
              className="mt-1 min-h-24 text-sm"
              value={reason}
              maxLength={REASON_LIMIT}
              disabled={pending}
              aria-label="审核原因"
              aria-invalid={Boolean(error) || undefined}
              placeholder={decision === 'rejected'
                ? '例如：营收下滑且存在未结诉讼，风险不可控'
                : decision === 'approved'
                  ? '例如：材料齐全，风险可控，同意按建议额度放款'
                  : '请先选择审核结论，再说明通过或拒绝的原因'}
              onChange={(event) => {
                setReason(event.target.value)
                if (error) setError('')
              }}
            />
            <span className="mt-1 block text-right font-mono text-[10px] text-muted-foreground">
              {reason.length}/{REASON_LIMIT}
            </span>
          </label>

          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t px-4 py-3">
          <Button type="button" variant="outline" size="sm" disabled={pending} onClick={onClose}>取消</Button>
          <Button
            type="button"
            size="sm"
            variant={decision === 'rejected' ? 'destructive' : 'default'}
            disabled={pending || !decision}
            onClick={() => void submit()}
          >
            {pending ? <Spinner /> : decision === 'rejected' ? <XIcon /> : <CheckIcon />}
            {decision === 'rejected' ? '确认拒绝' : decision === 'approved' ? '确认通过' : '提交审核'}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
