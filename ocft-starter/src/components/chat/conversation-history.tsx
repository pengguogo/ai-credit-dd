/**
 * 历史会话：搜索 + 分页滚动加载 + 虚拟列表，减轻长列表渲染压力。
 * 数据只来自后端；关闭按钮与点遮罩 / Esc 均可关掉。
 */
import { HistoryIcon, SearchIcon, XIcon } from 'lucide-react'
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { StatusBadge } from '@/components/status-badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { SCENARIOS } from '@/data/scenario'
import { ApiError, api } from '@/lib/api'
import { STATUS_META } from '@/lib/format'
import type { ConversationSummary, RunStatus } from '@/lib/types'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 30
const ROW_HEIGHT = 64
const OVERSCAN = 6

function formatWhen(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function isRunStatus(value: string | null): value is RunStatus {
  return value != null && value in STATUS_META
}

function scenarioLabel(scenarioId: string): string {
  return SCENARIOS.find((s) => s.id === scenarioId)?.name ?? scenarioId
}

function useDebounced(value: string, ms: number): string {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), ms)
    return () => window.clearTimeout(id)
  }, [value, ms])
  return debounced
}

export function ConversationHistory({ actorId, currentId, disabled, onOpen }: {
  actorId: string
  currentId: string | null
  disabled: boolean
  onOpen: (item: ConversationSummary) => Promise<string | null>
}) {
  const titleId = useId()
  const searchId = useId()
  const listRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const debouncedQuery = useDebounced(query, 280)
  const [items, setItems] = useState<ConversationSummary[]>([])
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [scrollTop, setScrollTop] = useState(0)
  const [viewportH, setViewportH] = useState(320)
  const requestSeq = useRef(0)

  const close = useCallback(() => {
    setOpen(false)
    setQuery('')
    setItems([])
    setTotal(0)
    setHasMore(false)
    setError('')
    setOpeningId(null)
    setScrollTop(0)
  }, [])

  const loadPage = useCallback(async (offset: number, q: string, append: boolean) => {
    const seq = ++requestSeq.current
    if (append) setLoadingMore(true)
    else {
      setLoading(true)
      setScrollTop(0)
      if (listRef.current) listRef.current.scrollTop = 0
    }
    try {
      const page = await api.conversations(actorId, {
        q: q || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      if (seq !== requestSeq.current) return
      setItems((prev) => (append ? [...prev, ...page.conversations] : page.conversations))
      setTotal(page.total)
      setHasMore(page.hasMore)
      setError('')
    } catch (exc: unknown) {
      if (seq !== requestSeq.current) return
      if (!append) setItems([])
      setError(exc instanceof ApiError ? exc.message : '历史会话加载失败')
    } finally {
      if (seq === requestSeq.current) {
        setLoading(false)
        setLoadingMore(false)
      }
    }
  }, [actorId])

  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => {
      void loadPage(0, debouncedQuery, false)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [open, actorId, debouncedQuery, loadPage])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, close])

  useEffect(() => {
    if (!open) return
    const el = listRef.current
    if (!el) return
    const measure = () => {
      window.requestAnimationFrame(() => {
        setViewportH(el.clientHeight || 320)
      })
    }
    measure()
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null
    ro?.observe(el)
    return () => ro?.disconnect()
  }, [open, loading])

  const virtual = useMemo(() => {
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN)
    const visible = Math.ceil(viewportH / ROW_HEIGHT) + OVERSCAN * 2
    const end = Math.min(items.length, start + visible)
    return { start, end, totalHeight: items.length * ROW_HEIGHT }
  }, [items.length, scrollTop, viewportH])

  const onListScroll = () => {
    const el = listRef.current
    if (!el) return
    setScrollTop(el.scrollTop)
    const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 96
    if (nearBottom && hasMore && !loading && !loadingMore && openingId == null) {
      void loadPage(items.length, debouncedQuery, true)
    }
  }

  const pick = async (item: ConversationSummary) => {
    setOpeningId(item.conversationId)
    setError('')
    const message = await onOpen(item)
    setOpeningId(null)
    if (message && message !== '已取消') {
      setError(message)
      return
    }
    if (!message) close()
  }

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={disabled}
        onClick={() => {
          setError('')
          setOpen(true)
        }}
      >
        <HistoryIcon />历史会话
      </Button>
      {open && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 py-12 sm:py-16"
          onMouseDown={close}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="flex max-h-[min(36rem,calc(100vh-6rem))] w-full max-w-md flex-col overflow-hidden rounded-xl bg-card text-card-foreground shadow-lg ring-1 ring-foreground/10"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="flex items-start gap-3 border-b px-4 py-3">
              <div className="min-w-0 flex-1">
                <h2 id={titleId} className="text-base font-medium">历史会话</h2>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  搜索标题，滚动加载更多；点一条续接对话。
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="shrink-0 cursor-pointer"
                aria-label="关闭历史会话"
                onClick={close}
              >
                <XIcon />
              </Button>
            </div>

            <div className="border-b px-3 py-2">
              <label htmlFor={searchId} className="sr-only">搜索历史会话</label>
              <div className="relative">
                <SearchIcon
                  aria-hidden
                  className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  id={searchId}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索会话标题…"
                  className="h-9 pr-9 pl-8"
                  autoComplete="off"
                />
                {query && (
                  <button
                    type="button"
                    className="absolute inset-y-0 right-0 flex w-9 cursor-pointer items-center justify-center text-muted-foreground hover:text-foreground"
                    aria-label="清空搜索"
                    onClick={() => setQuery('')}
                  >
                    <XIcon className="size-3.5" />
                  </button>
                )}
              </div>
              {!loading && !error && (
                <p className="mt-1.5 px-0.5 text-[11px] text-muted-foreground">
                  {total === 0
                    ? (debouncedQuery ? '没有匹配的会话' : '还没有历史会话')
                    : `共 ${total} 条 · 已加载 ${items.length} 条`}
                </p>
              )}
            </div>

            <div
              ref={listRef}
              className="min-h-0 flex-1 overflow-y-auto"
              onScroll={onListScroll}
            >
              {loading && items.length === 0 && (
                <p className="flex items-center gap-2 px-4 py-8 text-sm text-muted-foreground">
                  <Spinner />读取历史会话…
                </p>
              )}
              {!loading && error && items.length === 0 && (
                <p role="alert" className="px-4 py-6 text-sm text-destructive">{error}</p>
              )}
              {!loading && !error && items.length === 0 && (
                <p className="px-4 py-8 text-sm text-muted-foreground">
                  {debouncedQuery
                    ? `没有匹配「${debouncedQuery}」的会话`
                    : '还没有历史会话。提问之后会出现在这里。'}
                </p>
              )}
              {items.length > 0 && (
                <div className="relative w-full" style={{ height: virtual.totalHeight }}>
                  {items.slice(virtual.start, virtual.end).map((item, i) => {
                    const index = virtual.start + i
                    return (
                      <div
                        key={item.conversationId}
                        className="absolute right-0 left-0 px-2"
                        style={{ top: index * ROW_HEIGHT, height: ROW_HEIGHT }}
                      >
                        <HistoryRow
                          item={item}
                          current={item.conversationId === currentId}
                          pending={openingId === item.conversationId}
                          disabled={openingId != null}
                          onPick={() => void pick(item)}
                        />
                      </div>
                    )
                  })}
                </div>
              )}
              {loadingMore && (
                <p className="flex items-center justify-center gap-2 py-3 text-xs text-muted-foreground">
                  <Spinner className="size-3.5" />加载更多…
                </p>
              )}
              {error && items.length > 0 && (
                <p role="alert" className="px-4 py-2 text-xs text-destructive">{error}</p>
              )}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}

function HistoryRow({ item, current, pending, disabled, onPick }: {
  item: ConversationSummary
  current: boolean
  pending: boolean
  disabled: boolean
  onPick: () => void
}) {
  return (
    <button
      type="button"
      className={cn(
        'flex h-[56px] w-full items-start gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-muted disabled:opacity-60',
        current && 'bg-brand-soft',
      )}
      disabled={disabled}
      aria-current={current ? 'true' : undefined}
      onClick={onPick}
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm">{item.title}</span>
        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
          {scenarioLabel(item.scenarioId)} · {formatWhen(item.updatedAt)} · {item.turnCount} 轮
          {current ? ' · 当前' : ''}
        </span>
      </span>
      {pending ? <Spinner /> : isRunStatus(item.lastStatus) && <StatusBadge status={item.lastStatus} />}
    </button>
  )
}
