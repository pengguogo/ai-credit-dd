/**
 * 会话记忆：查看、纠正、清除（待办 0-6；评审维度②"记忆内容可查看、可纠正、可清除"）。
 * 展示的就是下一轮会带给模型的内容；数据只来自后端，每次修改后端写审计。
 */
import { BrainIcon, EraserIcon, SaveIcon, XIcon } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import { createPortal } from 'react-dom'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { ApiError, api } from '@/lib/api'
import { formatTime } from '@/lib/format'
import type { ConversationMemory, MemoryClearScope } from '@/lib/types'

/** 实体键的中文名；未列出的直接显示键名 */
const KEY_LABELS: Record<string, string> = {
  applicationId: '申请编号',
  customerName: '客户',
  txnId: '交易编号',
  accountId: '账户',
  claimId: '案件编号',
  insurant: '被保险人',
  docId: '文档编号',
  company: '公司',
  intentId: '意图',
}

const SEPARATOR = /[、,，]/

function toDraft(memory: ConversationMemory): Record<string, string> {
  return Object.fromEntries(memory.allowedKeys.map((key) => [key, (memory.entities[key] ?? []).join('、')]))
}

function parseValues(text: string): string[] {
  return text.split(SEPARATOR).map((v) => v.trim()).filter(Boolean)
}

function eventSummary(event: ConversationMemory['events'][number]): string {
  if (event.eventType === 'memory_cleared') {
    const scope = String(event.payload.scope)
    return scope === 'entities' ? '清除了实体' : scope === 'history' ? '清除了历史' : '清除了实体与历史'
  }
  const after = (event.payload.after ?? {}) as Record<string, string[]>
  const keys = Object.keys(after)
  return keys.length ? `纠正为 ${keys.map((k) => `${KEY_LABELS[k] ?? k}=${after[k].join('、')}`).join('；')}` : '清空了全部实体'
}

export function MemoryDialog({ actorId, conversationId, disabled }: {
  actorId: string
  conversationId: string | null
  disabled: boolean
}) {
  const titleId = useId()
  const [open, setOpen] = useState(false)
  const [memory, setMemory] = useState<ConversationMemory | null>(null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (!open || !conversationId) return
    let cancelled = false
    api.memory(actorId, conversationId)
      .then((m) => {
        if (cancelled) return
        setMemory(m)
        setDraft(toDraft(m))
        setError('')
      })
      .catch((exc: unknown) => {
        if (!cancelled) setError(exc instanceof ApiError ? exc.message : '记忆加载失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, actorId, conversationId])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const apply = async (label: string, action: () => Promise<ConversationMemory>, done: string) => {
    setPending(label)
    setError('')
    setNotice('')
    try {
      const m = await action()
      setMemory(m)
      setDraft(toDraft(m))
      setNotice(done)
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '操作失败')
    } finally {
      setPending(null)
    }
  }

  const changed = memory
    ? Object.fromEntries(memory.allowedKeys
      .filter((key) => parseValues(draft[key] ?? '').join('、') !== (memory.entities[key] ?? []).join('、'))
      .map((key) => [key, parseValues(draft[key] ?? '')]))
    : {}
  const hasChanges = Object.keys(changed).length > 0

  const save = () => {
    if (!memory || !conversationId || !hasChanges) return
    const willDrop = memory.allowedKeys.filter((k) => !(k in changed) && (memory.entities[k] ?? []).length > 0)
    const dropNote = willDrop.length
      ? `；${willDrop.map((k) => KEY_LABELS[k] ?? k).join('、')}已清空，下一轮会按新值重新查询`
      : ''
    void apply('save', () => api.correctMemory(actorId, conversationId, changed, memory.version),
      `已保存，下一轮提问按新值带给模型${dropNote}`)
  }

  const clear = (scope: MemoryClearScope, question: string) => {
    if (!memory || !conversationId || !window.confirm(question)) return
    void apply(scope, () => api.clearMemory(actorId, conversationId, scope, memory.version), '已清除')
  }

  return (
    <>
      <Button type="button" variant="ghost" size="sm" disabled={disabled || !conversationId}
        title={conversationId ? '查看、纠正、清除本会话的记忆' : '开始对话后才有记忆'}
        onClick={() => {
          setError('')
          setNotice('')
          setLoading(true)
          setOpen(true)
        }}>
        <BrainIcon />记忆
      </Button>
      {open && createPortal(
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 py-16" onMouseDown={() => setOpen(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="flex max-h-[min(36rem,calc(100vh-8rem))] w-full max-w-lg flex-col overflow-hidden rounded-xl bg-card text-card-foreground shadow-lg ring-1 ring-foreground/10"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="flex items-start gap-3 border-b px-4 py-3">
              <div className="min-w-0 flex-1">
                <h2 id={titleId} className="text-base font-medium">会话记忆</h2>
                <p className="mt-0.5 text-xs text-muted-foreground">这里的内容会在下一轮提问时带给模型。修改与清除都会留审计。</p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="shrink-0 cursor-pointer"
                aria-label="关闭会话记忆"
                onClick={() => setOpen(false)}
              >
                <XIcon />
              </Button>
            </div>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
              {loading && <p className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner />读取记忆…</p>}
              {!loading && error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              <p role="status" className={notice ? 'text-sm text-success' : 'sr-only'}>{notice}</p>
              {!loading && memory && (
                <>
                  <section aria-labelledby={`${titleId}-entities`} className="space-y-2">
                    <h3 id={`${titleId}-entities`} className="text-sm font-medium">已记住的实体</h3>
                    <p className="text-xs text-muted-foreground">
                      这些实体指向同一个对象。只改其中一项时，其余几项会清空，下一轮由系统按新值重新查询。
                    </p>
                    {memory.allowedKeys.length === 0 && (
                      <p className="text-xs text-muted-foreground">本场景没有需要跨轮记住的实体。</p>
                    )}
                    {memory.allowedKeys.map((key) => (
                      <div key={key} className="grid grid-cols-[6rem_1fr] items-center gap-2">
                        <label htmlFor={`${titleId}-${key}`} className="text-xs text-muted-foreground">{KEY_LABELS[key] ?? key}</label>
                        <Input
                          id={`${titleId}-${key}`}
                          value={draft[key] ?? ''}
                          maxLength={330}
                          placeholder="未记住；多个值用顿号分隔"
                          onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                        />
                      </div>
                    ))}
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button size="sm" onClick={save} disabled={!hasChanges || pending !== null}>
                        {pending === 'save' ? <Spinner /> : <SaveIcon />}保存纠正
                      </Button>
                      <Button size="sm" variant="outline" disabled={pending !== null}
                        onClick={() => clear('entities', '清除全部已记住的实体？')}>
                        {pending === 'entities' ? <Spinner /> : <EraserIcon />}清除实体
                      </Button>
                    </div>
                  </section>

                  <section aria-labelledby={`${titleId}-history`} className="space-y-1">
                    <h3 id={`${titleId}-history`} className="text-sm font-medium">带入模型的历史</h3>
                    <p className="text-xs text-muted-foreground">
                      共 {memory.totalMessages} 条消息，下一轮会带入其中 {memory.carriedMessages} 条
                      （超出预算时较早的会压缩成摘要）。清除后消息仍可在对话里查看，只是不再送给模型。
                    </p>
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button size="sm" variant="outline" disabled={pending !== null || memory.carriedMessages === 0}
                        onClick={() => clear('history', '此前的对话不再带给模型，确定清除？')}>
                        {pending === 'history' ? <Spinner /> : <EraserIcon />}清除历史
                      </Button>
                      <Button size="sm" variant="destructive" disabled={pending !== null}
                        onClick={() => clear('all', '清除全部实体和历史？')}>
                        {pending === 'all' ? <Spinner /> : <EraserIcon />}全部清除
                      </Button>
                    </div>
                  </section>

                  <section aria-labelledby={`${titleId}-confirmed`} className="space-y-1">
                    <h3 id={`${titleId}-confirmed`} className="text-sm font-medium">已确认的结论</h3>
                    {memory.confirmedConclusions.length === 0 ? (
                      <p className="text-xs text-muted-foreground">还没有经业务确认的结论。</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {memory.confirmedConclusions.map((c) => (
                          <li key={`${c.runId}-${c.answerVersion}`} className="rounded-md bg-muted/60 px-2 py-1.5 text-xs">
                            <span className="block text-muted-foreground">{formatTime(c.confirmedAt)} · {c.confirmedBy} · v{c.answerVersion}</span>
                            <span className="line-clamp-3">{c.answer}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  <section aria-labelledby={`${titleId}-events`} className="space-y-1">
                    <h3 id={`${titleId}-events`} className="text-sm font-medium">修改记录</h3>
                    {memory.events.length === 0 ? (
                      <p className="text-xs text-muted-foreground">没有人工修改过。</p>
                    ) : (
                      <ol className="space-y-1 text-xs">
                        {memory.events.map((e) => (
                          <li key={e.id}>
                            <span className="font-mono text-muted-foreground">{formatTime(e.createdAt)} · {e.actorId}</span>{' '}
                            {eventSummary(e)}
                          </li>
                        ))}
                      </ol>
                    )}
                  </section>
                </>
              )}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}
