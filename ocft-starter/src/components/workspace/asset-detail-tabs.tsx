/** 按档案关联的报告读取已保存的执行轨迹与证据，不重新运行尽调。 */
import { useEffect, useState } from 'react'
import { ActivityIcon, FileCheck2Icon } from 'lucide-react'

import { EvidenceList } from '@/components/run/evidence-list'
import { RunTrace } from '@/components/run/run-trace'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api, streamRunEvents } from '@/lib/api'
import type { Evidence, RunDetail, RunEvent } from '@/lib/types'

type Loaded<T> = { status: 'loading' } | { status: 'ready'; data: T } | { status: 'error'; message: string }
type SavedTrace = { run: RunDetail; events: RunEvent[] }

function LoadError({ message, retry }: { message: string; retry: () => void }) {
  return (
    <div role="alert" className="space-y-2 rounded-md border border-destructive/30 p-3 text-sm">
      <p>{message}</p>
      <Button size="sm" variant="outline" onClick={retry}>重新加载</Button>
    </div>
  )
}

export function AssetDetailTabs({ actorId, runId, traceSelectionVersion = 0 }: {
  actorId: string
  runId: string
  traceSelectionVersion?: number
}) {
  const [trace, setTrace] = useState<Loaded<SavedTrace>>({ status: 'loading' })
  const [evidence, setEvidence] = useState<Loaded<Evidence[]>>({ status: 'loading' })
  const [reload, setReload] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    // 延至下一任务开始加载，避免 effect 内同步更新状态。
    const timer = window.setTimeout(() => {
      setTrace({ status: 'loading' })
      setEvidence({ status: 'loading' })
      const events: RunEvent[] = []
      void Promise.all([
        api.getRun(actorId, runId),
        streamRunEvents(actorId, runId, event => { events.push(event) }, controller.signal),
      ]).then(([run]) => {
        if (!controller.signal.aborted) setTrace({ status: 'ready', data: { run, events } })
      }).catch((error: unknown) => {
        if (!controller.signal.aborted) setTrace({ status: 'error', message: error instanceof Error ? error.message : '生成轨迹加载失败' })
      })
      void api.getEvidence(actorId, runId).then(data => {
        if (!controller.signal.aborted) setEvidence({ status: 'ready', data })
      }).catch((error: unknown) => {
        if (!controller.signal.aborted) setEvidence({ status: 'error', message: error instanceof Error ? error.message : '证据加载失败' })
      })
    }, 0)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [actorId, runId, reload])

  const retry = () => setReload(value => value + 1)
  return (
    <Tabs key={traceSelectionVersion} defaultValue="trace" className="min-w-0">
      <TabsList className="w-full" aria-label="报告轨迹">
        <TabsTrigger value="trace"><ActivityIcon />生成轨迹</TabsTrigger>
        <TabsTrigger value="evidence"><FileCheck2Icon />证据{evidence.status === 'ready' ? ` ${evidence.data.length}` : ''}</TabsTrigger>
      </TabsList>
      <TabsContent value="trace" className="min-w-0 pt-3">
        {trace.status === 'loading' ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner />正在加载已保存的生成轨迹…</p>
        ) : trace.status === 'error' ? <LoadError message={trace.message} retry={retry} /> : (
          <RunTrace events={trace.data.events} traces={trace.data.run.toolTraces} live={false} />
        )}
      </TabsContent>
      <TabsContent value="evidence" className="min-w-0 pt-3">
        {evidence.status === 'loading' ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner />正在加载已保存的证据…</p>
        ) : evidence.status === 'error' ? <LoadError message={evidence.message} retry={retry} /> : (
          <EvidenceList evidence={evidence.data} loading={false} />
        )}
      </TabsContent>
    </Tabs>
  )
}
