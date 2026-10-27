/** 证据卡片：来源（表 / 主键 / 过滤条件）、内容哈希、数据版本，可展开当次快照。 */
import { ChevronDownIcon, FileSearchIcon } from 'lucide-react'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { formatTime } from '@/lib/format'
import type { Evidence } from '@/lib/types'

const SOURCE_LABEL: Record<string, string> = {
  db_query: '数据库查询',
  calculation: '规则计算',
  document: '文档片段',
}

function describeSource(ref: Record<string, unknown>): string {
  const parts: string[] = []
  if (typeof ref.table === 'string') parts.push(`表 ${ref.table}`)
  if (ref.keys && typeof ref.keys === 'object') {
    parts.push(Object.entries(ref.keys as Record<string, unknown>).map(([k, v]) => `${k}=${String(v)}`).join('，'))
  }
  if (ref.filters && typeof ref.filters === 'object') {
    const f = Object.entries(ref.filters as Record<string, unknown>).filter(([, v]) => v != null)
    if (f.length) parts.push(`条件 ${f.map(([k, v]) => `${k}=${String(v)}`).join('，')}`)
  }
  if (typeof ref.calc === 'string') parts.push(`规则 ${ref.calc}`)
  if (typeof ref.docId === 'string') parts.push(`文档 ${ref.docId}`)
  return parts.join(' · ') || JSON.stringify(ref)
}

export function EvidenceList({ evidence, loading }: { evidence: Evidence[] | null; loading: boolean }) {
  if (loading || evidence === null) {
    return <p className="text-sm text-muted-foreground">{loading ? '执行结束后加载证据…' : '暂无'}</p>
  }
  if (evidence.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon"><FileSearchIcon /></EmptyMedia>
          <EmptyTitle>本次执行没有证据</EmptyTitle>
          <EmptyDescription>没有取得数据时，Agent 不会给出结论。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  return (
    <ul className="space-y-2">
      {evidence.map((ev) => (
        <li key={ev.evidenceId} className="rounded-lg border bg-card">
          <Collapsible>
            <CollapsibleTrigger className="group flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-accent px-1.5 py-0.5 text-xs font-medium text-accent-foreground">
                    {SOURCE_LABEL[ev.sourceType] ?? ev.sourceType}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">{ev.evidenceId}</span>
                </div>
                <p className="text-sm break-all">{describeSource(ev.sourceRef)}</p>
                <p className="font-mono text-xs text-muted-foreground">
                  sha256 {ev.contentHash.slice(0, 12)}… · 数据版本 v{ev.dataVersion} · {formatTime(ev.createdAt)}
                </p>
              </div>
              <ChevronDownIcon aria-hidden className="mt-1 size-4 shrink-0 text-muted-foreground transition-transform group-aria-expanded:rotate-180" />
              <span className="sr-only">展开快照</span>
            </CollapsibleTrigger>
            <CollapsibleContent className="px-3 pb-3">
              <p className="mb-1 text-xs text-muted-foreground">当次数据快照</p>
              <pre className="max-h-72 overflow-auto rounded-md bg-muted px-2 py-1.5 font-mono text-xs">
                {JSON.stringify(ev.snapshot, null, 2)}
              </pre>
            </CollapsibleContent>
          </Collapsible>
        </li>
      ))}
    </ul>
  )
}
