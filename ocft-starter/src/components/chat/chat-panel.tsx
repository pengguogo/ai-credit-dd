/** 左侧对话：多轮会话、每轮的诚实状态展示、示例问题与输入框。 */
import {
  AlertTriangleIcon,
  BanIcon,
  CheckIcon,
  CopyIcon,
  FileTextIcon,
  HelpCircleIcon,
  MessageSquarePlusIcon,
  PanelLeftCloseIcon,
  SendIcon,
  ServerCrashIcon,
  SparklesIcon,
} from 'lucide-react'
import { useCallback, useEffect, useId, useRef, useState } from 'react'

import { ConversationHistory } from '@/components/chat/conversation-history'
import { MemoryDialog } from '@/components/chat/memory-dialog'
import { RoleLanes } from '@/components/run/role-lanes'
import { isFullReport, isReportGenerationQuestion } from '@/lib/answer-export'
import { Markdown } from '@/components/markdown'
import { approvalLabel, businessNarrative, generationLabel } from '@/components/report/preview/report-business'
import { reportData, text as reportText } from '@/components/report/preview/report-data'
import { DiligenceProgress } from '@/components/chat/diligence-progress'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle, CardAction } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Message, MessageContent, MessageHeader } from '@/components/ui/message'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { type ScenarioMeta } from '@/data/scenario'
import type { Turn } from '@/hooks/use-agent-session'
import { useRevealText } from '@/hooks/use-reveal-text'
import type { ConversationSummary } from '@/lib/types'
import { STATUS_META, parallelProbeDone, toolLabel } from '@/lib/format'
import { cn } from '@/lib/utils'

/** run 结束后把完整答案一点一点吐出；历史会话 / 无动画偏好则直接全文。 */
function RevealingMarkdown({ text, animate, onProgress, variant }: {
  text: string
  animate: boolean
  onProgress?: () => void
  variant?: 'default' | 'report'
}) {
  const { text: shown, done } = useRevealText(text, animate)
  const lastScrollAt = useRef(0)
  useEffect(() => {
    if (!animate || done) return
    const now = Date.now()
    // 节流跟滚，避免每帧 scrollIntoView 把主线程拖死
    if (now - lastScrollAt.current < 120) return
    lastScrollAt.current = now
    onProgress?.()
  }, [animate, done, shown, onProgress])
  return (
    <div aria-busy={!done}>
      <Markdown text={shown} variant={variant} />
      {!done && (
        <span
          aria-hidden
          className="ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 animate-pulse rounded-sm bg-brand/70"
        />
      )}
    </div>
  )
}

function AnswerMarkdown({ text, animate, onProgress }: {
  text: string
  animate: boolean
  onProgress?: () => void
}) {
  // key：答案就绪时重新挂载，保证打字机从空串开始。
  const markdown = (variant?: 'default' | 'report') => (
    <RevealingMarkdown
      key={animate ? `reveal:${text.length}:${text.slice(0, 24)}` : 'static'}
      text={variant === 'report' ? businessNarrative(text) : text}
      animate={animate}
      onProgress={onProgress}
      variant={variant}
    />
  )
  if (!isFullReport(text)) return markdown()
  // 完整尽调报告：卡片头展示报告标题，正文用报告样式（章节编号、深色表头）
  // 标题口径靠正文 scope 区分；此处只给通用免责，不默认写「额度」以免企业主体尽调被误读
  return (
    <article className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      <header className="flex items-center gap-3 border-b border-border bg-gradient-to-r from-brand-soft to-transparent px-4 py-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand text-white"><FileTextIcon className="size-4" /></span>
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold tracking-wide text-foreground">企业智能信贷尽调报告</h2>
          <p className="text-xs text-muted-foreground">工具测算结果 · 非授信审批，最终以业务审批为准</p>
        </div>
      </header>
      <div className="px-4 py-4">{markdown('report')}</div>
    </article>
  )
}

function liveStep(turn: Turn): string {
  const last = turn.events.at(-1)
  if (!turn.runId) return '提交中…'
  if (!last) return '等待执行…'
  if (last.type === 'tool_started') return `正在${toolLabel(last.toolName)}…`
  if (last.type === 'tool_finished') return `${toolLabel(last.toolName)}完成，模型继续推理…`
  return '模型推理中…'
}

function AnswerExport({ turn, answer }: { turn: Turn; answer: string }) {
  const [busy, setBusy] = useState<'copy' | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')
  if (!answer.trim()) return null

  async function copyAnswer() {
    setBusy('copy')
    setError('')
    try {
      await navigator.clipboard.writeText(answer)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setError('复制失败，请重试')
    } finally {
      setBusy(null)
    }
  }

  const showReportPreview = isReportGenerationQuestion(turn.question)
  return (
    <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
      <Button type="button" variant="outline" size="xs" className="cursor-pointer" disabled={busy !== null} onClick={() => void copyAnswer()}>
        {copied ? <CheckIcon /> : <CopyIcon />}
        {busy === 'copy' ? '正在复制…' : copied ? '已复制' : '复制'}
      </Button>
      {showReportPreview ? (
        <Button type="button" variant="outline" size="xs" className="cursor-pointer" disabled={!turn.runId} onClick={() => {
          if (turn.runId) window.open(`/report-preview.html?runId=${encodeURIComponent(turn.runId)}`, '_blank', 'noopener,noreferrer')
        }}>
          <FileTextIcon />预览报告
        </Button>
      ) : null}
      {error ? <span className="w-full text-right text-xs text-destructive">{error}</span> : null}
    </div>
  )
}

function ReportOutcome({ turn }: { turn: Turn }) {
  if (!turn.detail || !isFullReport(turn.detail.answer ?? '')) return null
  const data = reportData(turn.evidence ?? [])
  const enterpriseScope = data.scope === 'enterprise'
  const unit = reportText(data.credit.unit)
  const suggested = reportText(data.credit.suggestedCreditAmount ?? data.report.suggestedCreditAmount)
  return <div className={cn('grid gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs', enterpriseScope ? 'sm:grid-cols-2' : 'sm:grid-cols-3')}>
    <div><p className="text-muted-foreground">报告生成</p><p className="mt-1 font-medium">{generationLabel(turn.detail.status)}</p></div>
    <div>
      <p className="text-muted-foreground">尽调建议</p>
      <p className="mt-1 font-medium">
        {reportText(data.rating.riskLevel ?? data.report.riskLevel)}
        {' · '}建议授信额度 {suggested} {unit}
        {!enterpriseScope && (
          <>{' · '}申请额度 {reportText(data.credit.applyAmount)} {unit}</>
        )}
      </p>
    </div>
    {!enterpriseScope && (
      <div>
        <p className="text-muted-foreground">贷款审批</p>
        <p className="mt-1 font-medium">{approvalLabel(data.loanSnapshot.status)}</p>
        <p className="mt-1 text-muted-foreground">{data.loanEvidence ? '报告查询时快照，当前状态请查看审批表' : '缺少申请状态快照，请查看审批表'}</p>
      </div>
    )}
  </div>
}

function AssistantBody({ turn, onStreamProgress }: { turn: Turn; onStreamProgress?: () => void }) {
  const d = turn.detail
  if (turn.error) {
    return (
      <Alert variant="destructive">
        <ServerCrashIcon />
        <AlertTitle>请求未完成</AlertTitle>
        <AlertDescription>{turn.error.message}<span className="ml-1 font-mono text-xs">（{turn.error.code}）</span></AlertDescription>
      </Alert>
    )
  }
  if (turn.status === 'running' || !d) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner /> {turn.status === 'running' ? liveStep(turn) : '加载结果…'}
      </p>
    )
  }
  const missing = d.contextSnapshot.missingInfo ?? []
  switch (d.status) {
    case 'succeeded':
    case 'needs_confirmation':
      return (
        <div className="space-y-2">
          <ReportOutcome turn={turn} />
          <AnswerMarkdown text={d.answer ?? ''} animate={turn.revealAnswer} onProgress={onStreamProgress} />
          <p className="text-xs text-muted-foreground">
            依据 {d.evidenceIds.length} 条证据
            {d.status === 'needs_confirmation' && ' · 报告结论待业务确认，不代表贷款审批'}
          </p>
          <AnswerExport turn={turn} answer={d.answer ?? ''} />
        </div>
      )
    case 'needs_clarification':
      return (
        <Alert className="border-warning/40">
          <HelpCircleIcon className="text-warning" />
          <AlertTitle>Agent 需要你补充信息</AlertTitle>
          <AlertDescription className="space-y-1 text-foreground">
            <AnswerMarkdown text={d.errorMessage ?? ''} animate={turn.revealAnswer} onProgress={onStreamProgress} />
            <p className="text-xs text-muted-foreground">
              {missing.length > 0 && <>缺少：{missing.join('、')}。</>}直接在下方回复即可继续本次会话。
            </p>
          </AlertDescription>
        </Alert>
      )
    case 'insufficient_evidence':
      return (
        <Alert className="border-warning/40">
          <AlertTriangleIcon className="text-warning" />
          <AlertTitle>证据不足，未给出结论</AlertTitle>
          <AlertDescription className="space-y-1 text-foreground">
            <AnswerMarkdown text={d.errorMessage ?? ''} animate={turn.revealAnswer} onProgress={onStreamProgress} />
            {missing.length > 0 && <p className="text-xs text-muted-foreground">原因：{missing.join('；')}</p>}
          </AlertDescription>
        </Alert>
      )
    case 'blocked':
      return (
        <Alert variant="destructive">
          <BanIcon />
          <AlertTitle>已被合规规则拦截</AlertTitle>
          <AlertDescription>{d.errorMessage}<span className="block font-mono text-xs">{d.errorCode}</span></AlertDescription>
        </Alert>
      )
    default:
      return (
        <Alert variant="destructive">
          <ServerCrashIcon />
          <AlertTitle>{STATUS_META[d.status].hint}</AlertTitle>
          <AlertDescription>{d.errorMessage ?? '未返回原因'}<span className="block font-mono text-xs">{d.errorCode}</span></AlertDescription>
        </Alert>
      )
  }
}

function slashItems(scenario: ScenarioMeta, query: string) {
  const all = [
    ...scenario.mainSuggestions.map((item) => ({ ...item, group: '示例问题' })),
    ...scenario.edgeSuggestions.map((item) => ({ ...item, group: '异常路径' })),
  ]
  const needle = query.trim().toLowerCase()
  if (!needle) return all
  return all.filter((item) => item.tool.toLowerCase().includes(needle) || item.question.toLowerCase().includes(needle))
}

function SlashMenu({ scenario, query, active, onPick }: {
  scenario: ScenarioMeta
  query: string
  active: number
  onPick: (question: string) => void
}) {
  const items = slashItems(scenario, query)
  return (
    <div
      id="slash-menu"
      role="listbox"
      aria-label="示例问题"
      className="absolute bottom-full left-0 z-20 mb-2 max-h-96 w-full overflow-y-auto rounded-xl border bg-popover p-1.5 shadow-lg"
    >
      {items.length === 0 ? (
        <p className="px-2 py-3 text-xs text-muted-foreground">没有匹配「{query.trim()}」的示例</p>
      ) : items.map((item, index) => {
        const showGroup = index === 0 || items[index - 1].group !== item.group
        return (
          <div key={`${item.group}:${item.tool}:${item.question}`}>
            {showGroup && (
              <p className="px-2 pt-1.5 pb-1 text-[11px] text-muted-foreground">{item.group}</p>
            )}
            <button
              id={`slash-opt-${index}`}
              type="button"
              role="option"
              aria-selected={index === active}
              className={cn(
                'flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-xs',
                index === active ? 'bg-muted' : 'hover:bg-muted/70',
              )}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => onPick(item.question)}
            >
              <span className="mt-0.5 shrink-0 rounded-md bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{item.tool}</span>
              <span className="text-foreground">{item.question}</span>
            </button>
          </div>
        )
      })}
    </div>
  )
}

export function ChatPanel({ scenario, actorId, turns, busy, conversationId, selectedId, processId, onBindFillQuestion, onInputChange, onSelect, onAsk, onReset, onOpenConversation, onCollapse }: {
  scenario: ScenarioMeta
  actorId: string
  turns: Turn[]
  busy: boolean
  conversationId: string | null
  selectedId: string | null
  /** 正在右边查看详情的轮次。 */
  processId: string | null
  /** 把「填入输入框」的方法交给外层（左侧表格点击时调用）。 */
  onBindFillQuestion?: (fill: (question: string) => void) => void
  /** 同步输入框内容，供左侧企业编号气泡预览。 */
  onInputChange?: (value: string) => void
  onSelect: (id: string) => void
  onAsk: (q: string, images: string[]) => void
  onReset: () => void
  onOpenConversation: (item: ConversationSummary) => Promise<string | null>
  onCollapse?: () => void
}) {
  const [input, setInput] = useState('')
  const [slashDismissed, setSlashDismissed] = useState(false)
  const [slashActive, setSlashActive] = useState(0)
  const endRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const autoFollowRef = useRef(true)
  const scrollTurnRef = useRef<string | null>(null)
  /** 程序化跟滚期间忽略 onScroll，避免内容增高被误判成「用户上翻」而关掉跟滚 */
  const programmaticScrollRef = useRef(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const inputId = useId()

  const onInputChangeRef = useRef(onInputChange)
  useEffect(() => {
    onInputChangeRef.current = onInputChange
  }, [onInputChange])

  const writeInput = (value: string) => {
    setInput(value)
    onInputChangeRef.current?.(value)
  }

  const scrollToEnd = useCallback(() => {
    const el = listRef.current
    if (!el) {
      endRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' })
      return
    }
    programmaticScrollRef.current = true
    el.scrollTop = el.scrollHeight
    window.requestAnimationFrame(() => {
      programmaticScrollRef.current = false
    })
  }, [])

  const lastTurn = turns.at(-1)
  const parallelDone = lastTurn ? parallelProbeDone(lastTurn.events) : false
  // 并行三步未完成前不自动滚；完成后跟里程碑（含角色启动，否则报告 Agent 开跑时停在半截）。
  // scrollCue 必须是稳定字符串：绝不能把 lastTurn 对象放进 effect 依赖（每条 SSE 都换引用会滚到卡死）。
  const followScroll = Boolean(
    lastTurn && (lastTurn.status !== 'running' || parallelDone || lastTurn.detail || lastTurn.error),
  )
  const progressSig = lastTurn
    ? lastTurn.events.filter((e) =>
        e.type === 'plan_ready'
        || e.type === 'role_started'
        || e.type === 'role_finished'
        || e.type === 'verify_finished'
        || e.type === 'run_finished',
      ).length
    : 0
  const scrollCue = lastTurn
    ? [
        lastTurn.id,
        followScroll ? 'f1' : 'f0',
        followScroll ? String(progressSig) : '0',
        lastTurn.detail ? 'd' : '-',
        lastTurn.error ? 'e' : '-',
      ].join(':')
    : ''

  useEffect(() => {
    if (!scrollCue) return
    const [turnId, flag] = scrollCue.split(':')
    if (scrollTurnRef.current !== turnId) {
      scrollTurnRef.current = turnId
      autoFollowRef.current = true
    }
    if (!autoFollowRef.current) return
    if (flag !== 'f1') {
      // 新提问时把本轮滚进可视区一次；并行阶段 cue 不变，不会反复滚
      document.getElementById(`turn-${turnId}`)?.scrollIntoView({ behavior: 'auto', block: 'nearest' })
      return
    }
    scrollToEnd()
  }, [scrollCue, scrollToEnd])

  // 答案渐进显示时跟滚（已在 RevealingMarkdown 内节流）
  const onStreamProgress = useCallback(() => {
    if (!autoFollowRef.current) return
    scrollToEnd()
  }, [scrollToEnd])

  useEffect(() => {
    onBindFillQuestion?.((question) => {
      setSlashDismissed(false)
      setInput(question)
      onInputChangeRef.current?.(question)
      window.setTimeout(() => inputRef.current?.focus(), 0)
    })
  }, [onBindFillQuestion])

  const slashQuery = input.startsWith('/') ? input.slice(1) : ''
  const slashOpen = input.startsWith('/') && !slashDismissed
  const slashChoices = slashOpen ? slashItems(scenario, slashQuery) : []

  useEffect(() => {
    document.getElementById(`slash-opt-${slashActive}`)?.scrollIntoView({ block: 'nearest' })
  }, [slashActive, slashOpen])

  const fillInput = (q: string) => {
    setSlashDismissed(false)
    writeInput(q)
    inputRef.current?.focus()
  }

  const send = (q: string) => {
    if (!q.trim() || busy) return
    onAsk(q, [])
    writeInput('')
  }


  return (
    <Card className="h-full gap-2 pt-0 text-card-foreground">
      <CardHeader className="flex flex-row items-center justify-between border-b border-border/70 bg-tech-soft/35 py-1.5 [.border-b]:pb-1.5">
        <CardTitle className="tracking-tight">企业信贷智能体</CardTitle>
        <CardAction className="flex items-center gap-1">
          <ConversationHistory
            actorId={actorId}
            currentId={conversationId}
            disabled={busy}
            onOpen={onOpenConversation}
          />
          <MemoryDialog actorId={actorId} conversationId={conversationId} disabled={busy} />
          <Button variant="ghost" size="sm" onClick={onReset} disabled={turns.length === 0 || busy}>
            <MessageSquarePlusIcon />新会话
          </Button>
          {onCollapse && (
            <Button type="button" variant="ghost" size="icon-sm" aria-label="收起企业信贷智能体" onClick={onCollapse}>
              <PanelLeftCloseIcon />
            </Button>
          )}
        </CardAction>
      </CardHeader>
      <CardContent
        ref={listRef}
        className="min-h-0 flex-1 overflow-y-auto bg-transparent"
        onWheel={(event) => {
          if (event.deltaY < 0) autoFollowRef.current = false
        }}
        onTouchMove={() => { autoFollowRef.current = false }}
        onScroll={(event) => {
          if (programmaticScrollRef.current) return
          const element = event.currentTarget
          // 报告 Agent 成文时内容会突然变高；阈值略放宽，避免刚跟到底就被判定离开底部
          autoFollowRef.current = element.scrollHeight - element.scrollTop - element.clientHeight < 96
        }}>

        {turns.length === 0 ? (
          <Empty className="h-full">
            <EmptyHeader>
              <EmptyMedia variant="icon"><SparklesIcon /></EmptyMedia>
              <EmptyTitle>{scenario.emptyTitle}</EmptyTitle>
              <EmptyDescription>{scenario.emptyDescription}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <ol className="space-y-5" aria-label="会话记录">
            {turns.map((turn) => (
              <li key={turn.id} id={`turn-${turn.id}`} className="space-y-3">
                <Message align="end">
                  <MessageContent>
                    <div className="max-w-[85%] space-y-1.5 rounded-xl bg-brand-soft px-3 py-2 text-sm">
                      {turn.images.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {turn.images.map((src, i) => (
                            <img key={i} src={src} alt={`附件 ${i + 1}`} className="size-16 rounded-md border object-cover" />
                          ))}
                        </div>
                      )}
                      <p className="whitespace-pre-wrap">{turn.question}</p>
                    </div>
                  </MessageContent>
                </Message>
                <Message>
                  <MessageContent>
                    <div
                      className={cn(
                        'w-full rounded-xl border bg-card px-3 py-2.5 transition-colors',
                        selectedId === turn.id && 'border-brand/60 ring-1 ring-brand/20',
                      )}
                    >
                      <MessageHeader className={cn('mb-2 gap-3 px-0',
                        isReportGenerationQuestion(turn.question) && 'sticky top-0 z-20 border-b border-border/70 bg-card py-2')}>
                        {isReportGenerationQuestion(turn.question) && <DiligenceProgress turn={turn} />}
                        <Button
                          variant="ghost"
                          size="xs"
                          className="ml-auto"
                          onClick={() => onSelect(turn.id)}
                          aria-pressed={processId === turn.id}
                          aria-expanded={processId === turn.id}
                        >
                          {processId === turn.id ? '收起' : '查看详情'}
                        </Button>
                      </MessageHeader>
                      <RoleLanes events={turn.events} live={turn.status === 'running'} />
                      <AssistantBody turn={turn} onStreamProgress={onStreamProgress} />
                    </div>
                  </MessageContent>
                </Message>
              </li>
            ))}
          </ol>
        )}
        <div ref={endRef} />
      </CardContent>
      <CardFooter className="flex-col items-stretch gap-2.5 border-border/70 bg-tech-soft/25">
        <form
          className="relative flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (slashOpen && slashChoices[slashActive]) {
              fillInput(slashChoices[slashActive].question)
              return
            }
            send(input)
          }}
        >
          {slashOpen && (
            <SlashMenu scenario={scenario} query={slashQuery} active={slashActive} onPick={fillInput} />
          )}
          <label htmlFor={inputId} className="sr-only">输入问题</label>
          <Textarea
            ref={inputRef}
            id={inputId}
            value={input}
            aria-expanded={slashOpen}
            aria-controls={slashOpen ? 'slash-menu' : undefined}
            onChange={(e) => {
              setSlashDismissed(false)
              setSlashActive(0)
              writeInput(e.target.value)
            }}
            onKeyDown={(e) => {
              if (slashOpen && e.key === 'ArrowDown') {
                e.preventDefault()
                setSlashActive((index) => Math.min(index + 1, Math.max(slashChoices.length - 1, 0)))
                return
              }
              if (slashOpen && e.key === 'ArrowUp') {
                e.preventDefault()
                setSlashActive((index) => Math.max(index - 1, 0))
                return
              }
              if (slashOpen && e.key === 'Escape') {
                e.preventDefault()
                setSlashDismissed(true)
                return
              }
              if (slashOpen && e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                if (slashChoices[slashActive]) fillInput(slashChoices[slashActive].question)
                return
              }
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                send(input)
              }
            }}
            maxLength={2000}
            className="max-h-32 min-h-10 bg-card"
          />
          <Button type="submit" size="lg" disabled={busy || !input.trim()} aria-label="发送">
            {busy ? <Spinner /> : <SendIcon />}
          </Button>
        </form>
      </CardFooter>
    </Card>
  )
}
