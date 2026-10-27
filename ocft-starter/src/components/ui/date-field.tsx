import { Popover } from '@base-ui/react/popover'
import { CalendarIcon, ChevronLeftIcon, ChevronRightIcon } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

function parseIso(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim())
  if (!m) return null
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return Number.isNaN(d.getTime()) ? null : d
}

function toIso(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate()
}

function monthMatrix(year: number, month: number): (Date | null)[] {
  const first = new Date(year, month, 1)
  // 周一为一周起始：getDay() 日=0 → 偏移 6
  const startOffset = (first.getDay() + 6) % 7
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells: (Date | null)[] = []
  for (let i = 0; i < startOffset; i++) cells.push(null)
  for (let day = 1; day <= daysInMonth; day++) cells.push(new Date(year, month, day))
  while (cells.length % 7 !== 0) cells.push(null)
  while (cells.length < 42) cells.push(null)
  return cells
}

/** 日期字段：Popover + 月历，不使用原生 date input。 */
export function DateField({
  value,
  onValueChange,
  disabled,
  className,
  'aria-label': ariaLabel,
  placeholder = '选择日期',
}: {
  value: string
  onValueChange: (value: string) => void
  disabled?: boolean
  className?: string
  'aria-label'?: string
  placeholder?: string
}) {
  const selected = parseIso(value)
  const [today] = useState(() => {
    const d = new Date()
    return new Date(d.getFullYear(), d.getMonth(), d.getDate())
  })
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(() => selected ?? today)
  const cells = useMemo(
    () => monthMatrix(cursor.getFullYear(), cursor.getMonth()),
    [cursor],
  )
  const title = `${cursor.getFullYear()} 年 ${cursor.getMonth() + 1} 月`

  return (
    <Popover.Root
      open={open}
      modal
      onOpenChange={(next) => {
        if (disabled) return
        setOpen(next)
        if (next) setCursor(selected ?? today)
      }}
    >
      <Popover.Trigger
        disabled={disabled}
        aria-label={ariaLabel}
        className={cn(
          'flex h-8 w-full min-w-0 items-center justify-between gap-2 rounded-lg border border-input bg-transparent px-2.5 text-left text-xs outline-none transition-colors',
          'hover:bg-muted/40 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
          'data-popup-open:border-ring data-popup-open:ring-3 data-popup-open:ring-ring/50',
          'disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50',
          className,
        )}
      >
        <span className={cn('min-w-0 flex-1 truncate font-mono', !selected && 'text-muted-foreground')}>
          {selected ? toIso(selected) : placeholder}
        </span>
        <CalendarIcon className="size-3.5 shrink-0 text-muted-foreground opacity-70" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner className="z-[70] outline-none" sideOffset={4}>
          <Popover.Popup
            className={cn(
              'surface-panel-solid w-[17.5rem] origin-[var(--transform-origin)] rounded-xl border border-border/80 p-3 shadow-lg outline-none',
              'transition-[transform,opacity] duration-100 data-starting-style:scale-[0.98] data-starting-style:opacity-0 data-ending-style:scale-[0.98] data-ending-style:opacity-0',
            )}
          >
            <div className="mb-2 flex items-center justify-between gap-1">
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label="上个月"
                onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
              >
                <ChevronLeftIcon />
              </Button>
              <p className="text-sm font-medium tracking-tight">{title}</p>
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label="下个月"
                onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
              >
                <ChevronRightIcon />
              </Button>
            </div>
            <div className="mb-1 grid grid-cols-7 gap-0.5 text-center text-[10px] text-muted-foreground">
              {WEEKDAYS.map((d) => <span key={d} className="py-1">{d}</span>)}
            </div>
            <div className="grid grid-cols-7 gap-0.5">
              {cells.map((day, i) => {
                if (!day) return <span key={`e-${i}`} className="size-8" />
                const isSelected = selected ? sameDay(day, selected) : false
                const isToday = sameDay(day, today)
                return (
                  <button
                    key={toIso(day)}
                    type="button"
                    className={cn(
                      'inline-flex size-8 cursor-pointer items-center justify-center rounded-lg text-xs transition-colors',
                      isSelected
                        ? 'bg-brand font-medium text-white'
                        : isToday
                          ? 'bg-brand-soft font-medium text-brand'
                          : 'hover:bg-muted',
                    )}
                    onClick={() => {
                      onValueChange(toIso(day))
                      setOpen(false)
                    }}
                  >
                    {day.getDate()}
                  </button>
                )
              })}
            </div>
            <div className="mt-2 flex items-center justify-between border-t border-border/60 pt-2">
              <Button
                type="button"
                variant="ghost"
                size="xs"
                onClick={() => {
                  onValueChange(toIso(today))
                  setCursor(today)
                  setOpen(false)
                }}
              >
                今天
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                disabled={!value}
                onClick={() => {
                  onValueChange('')
                  setOpen(false)
                }}
              >
                清除
              </Button>
            </div>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}
