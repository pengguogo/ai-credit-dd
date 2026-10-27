import { diligenceProgress } from '@/lib/dd-progress'
import type { Turn } from '@/hooks/use-agent-session'
import { cn } from '@/lib/utils'

const STATE_LABELS = {
  waiting: '未完成', running: '执行中', ok: '已完成',
  degraded: '降级，待核查', skipped: '本轮跳过', failed: '未成功',
}

export function DiligenceProgress({ turn }: { turn: Turn }) {
  const { stages, completed } = diligenceProgress(turn.events, turn.status, turn.error ? null : turn.detail?.answer)
  return (
    <div className="min-w-0 flex-1" role="progressbar" aria-label="尽调进度" aria-valuemin={0} aria-valuemax={7} aria-valuenow={completed}
      aria-valuetext={`${completed}/7，${stages.map(stage => `${stage.label}${STATE_LABELS[stage.state]}`).join('，')}`}>
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="text-foreground">尽调进度</span>
        <span className="tabular-nums text-muted-foreground">{completed}/7</span>
      </div>
      <div className="grid grid-cols-7 gap-1.5">
        {stages.map(stage => (
          <div key={stage.id} title={`${stage.label} · ${STATE_LABELS[stage.state]}`} className="min-w-0">
            <div className={cn('h-1.5 rounded-full bg-muted', stage.state === 'ok' && 'bg-brand',
              (stage.state === 'degraded' || stage.state === 'failed') && 'bg-warning/60')} />
            <div className={cn('mt-1 truncate text-center text-[10px] leading-4 text-muted-foreground',
              stage.state === 'ok' && 'font-medium text-brand')}>{stage.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
