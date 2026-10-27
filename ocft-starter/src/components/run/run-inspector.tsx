/** 右侧检查器：选中一轮问答的轨迹 / 证据，以及可复核的元信息。 */
import { ActivityIcon, FileCheck2Icon, PanelRightCloseIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'

import { EvidenceList } from '@/components/run/evidence-list'
import { RunTrace } from '@/components/run/run-trace'
import { StatusBadge } from '@/components/status-badge'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { Turn } from '@/hooks/use-agent-session'
import { formatMs } from '@/lib/format'

export function RunInspector({ turn, onCollapse }: {
  turn: Turn | null
  onCollapse: () => void
}) {
  if (!turn) {
    return (
      <Card className="h-full gap-2 pt-0">
        <CardHeader className="flex flex-row items-center justify-between border-b border-border/70 bg-tech-soft/35 py-1.5 [.border-b]:pb-1.5">
          <CardTitle className="tracking-tight">执行过程</CardTitle>
          <CardAction>
            <CollapseInspector onCollapse={onCollapse} />
          </CardAction>
        </CardHeader>
        <CardContent className="flex h-full items-center">
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"><ActivityIcon /></EmptyMedia>
              <EmptyTitle>执行过程会显示在这里</EmptyTitle>
              <EmptyDescription>每一步工具调用和取得的证据都来自后端真实执行。</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </CardContent>
      </Card>
    )
  }
  const live = turn.status === 'running'
  const detail = turn.detail
  const runDuration = turn.events.find((e) => e.type === 'run_finished')
  return (
    <Card id="run-inspector" className="h-full gap-2 pt-0">
      <CardHeader className="border-b border-border/70 bg-tech-soft/35 py-1.5 [.border-b]:pb-1.5">
        <CardTitle className="flex items-center gap-2 tracking-tight">
          执行详情 <StatusBadge status={turn.status} />
        </CardTitle>
        <CardAction>
          <CollapseInspector onCollapse={onCollapse} />
        </CardAction>
        <CardDescription className="truncate" title={turn.question}>{turn.question}</CardDescription>
        <dl className="col-span-full mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-xs text-muted-foreground">
          <dt className="sr-only">runId</dt><dd className="truncate">{turn.runId ?? '分配中…'}</dd>
          <dt className="sr-only">模型</dt><dd className="truncate">{detail?.model ?? '—'}</dd>
          <dt className="sr-only">耗时</dt>
          <dd>耗时 {formatMs(runDuration?.type === 'run_finished' ? runDuration.durationMs : undefined)}</dd>
          <dt className="sr-only">token</dt><dd>{detail ? `${detail.usage.totalTokens} tokens` : '—'}</dd>
          {detail?.contextSnapshot.requestId && (
            <><dt className="sr-only">请求 ID</dt><dd className="col-span-2 truncate">请求 {detail.contextSnapshot.requestId}</dd></>
          )}
        </dl>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto">
        <Tabs defaultValue="trace">
          <TabsList className="w-full">
            <TabsTrigger value="trace"><ActivityIcon />轨迹</TabsTrigger>
            <TabsTrigger value="evidence"><FileCheck2Icon />证据{turn.evidence ? ` ${turn.evidence.length}` : ''}</TabsTrigger>
          </TabsList>
          <TabsContent value="trace" className="pt-3">
            <RunTrace events={turn.events} traces={detail?.toolTraces ?? []} live={live} />
            {detail?.contextSnapshot.toolSummaryRuns?.length ? (
              <p className="mt-4 text-xs text-muted-foreground">
                已带入前序 {detail.contextSnapshot.toolSummaryRuns.length} 轮的工具结果摘要
                {detail.contextSnapshot.entities?.applicationId?.length
                  ? `；会话实体：${detail.contextSnapshot.entities.applicationId.join('、')}` : ''}
              </p>
            ) : null}
          </TabsContent>
          <TabsContent value="evidence" className="pt-3">
            <EvidenceList evidence={turn.evidence} loading={live} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}

function CollapseInspector({ onCollapse }: { onCollapse: () => void }) {
  return (
    <Button type="button" variant="ghost" size="icon-sm" aria-label="收起执行过程" onClick={onCollapse}>
      <PanelRightCloseIcon />
    </Button>
  )
}
