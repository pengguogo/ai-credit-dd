import { cn } from '@/lib/utils'
import { STATUS_META, TONE_CLASS } from '@/lib/format'
import type { RunStatus } from '@/lib/types'

export function StatusBadge({ status, className }: { status: RunStatus; className?: string }) {
  const meta = STATUS_META[status]
  return (
    <span
      className={cn(
        'inline-flex h-5 items-center gap-1 rounded-full px-2 text-xs font-medium whitespace-nowrap',
        TONE_CLASS[meta.tone],
        className,
      )}
    >
      {status === 'running' && <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-current" />}
      {meta.label}
    </span>
  )
}
