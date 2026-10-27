import { Popover } from '@base-ui/react/popover'
import { Select as SelectPrimitive } from '@base-ui/react/select'
import { CheckIcon, ChevronDownIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type SelectOption = { value: string; label: ReactNode }

const triggerClass = cn(
  'flex h-8 w-full min-w-0 items-center justify-between gap-2 rounded-lg border border-input bg-transparent px-2.5 text-left text-xs outline-none transition-colors',
  'hover:bg-muted/40 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
  'data-popup-open:border-ring data-popup-open:ring-3 data-popup-open:ring-ring/50',
  'data-disabled:pointer-events-none data-disabled:cursor-not-allowed data-disabled:bg-input/50 data-disabled:opacity-50',
)

/** 表单下拉：Base UI Select，外观对齐 Input。 */
export function SelectField({
  value,
  onValueChange,
  options,
  placeholder = '请选择',
  disabled,
  className,
  'aria-label': ariaLabel,
  mono = false,
}: {
  value: string
  onValueChange: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  disabled?: boolean
  className?: string
  'aria-label'?: string
  mono?: boolean
}) {
  const items = Object.fromEntries(options.map((o) => [o.value, o.label]))
  const selected = value === '' ? null : value

  return (
    <SelectPrimitive.Root
      value={selected}
      onValueChange={(next) => onValueChange(next == null ? '' : String(next))}
      items={items}
      disabled={disabled}
      modal
    >
      <SelectPrimitive.Trigger
        className={cn(triggerClass, className)}
        aria-label={ariaLabel}
      >
        <SelectPrimitive.Value
          placeholder={placeholder}
          className={cn(
            'min-w-0 flex-1 truncate data-placeholder:text-muted-foreground',
            mono && 'font-mono',
          )}
        />
        <SelectPrimitive.Icon className="shrink-0 text-muted-foreground">
          <ChevronDownIcon className="size-3.5 opacity-70" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Positioner className="z-[70] outline-none" sideOffset={4} alignItemWithTrigger={false}>
          <SelectPrimitive.Popup
            className={cn(
              'surface-panel-solid max-h-[min(16rem,var(--available-height))] min-w-[var(--anchor-width)] origin-[var(--transform-origin)] overflow-hidden rounded-lg border border-border/80 shadow-lg',
              'transition-[transform,opacity] duration-100 data-starting-style:scale-[0.98] data-starting-style:opacity-0 data-ending-style:scale-[0.98] data-ending-style:opacity-0',
            )}
          >
            <SelectPrimitive.List className="max-h-[min(16rem,var(--available-height))] overflow-y-auto py-1 outline-none">
              {options.length === 0 ? (
                <div className="px-3 py-2 text-xs text-muted-foreground">暂无选项</div>
              ) : (
                options.map((opt) => (
                  <SelectPrimitive.Item
                    key={opt.value}
                    value={opt.value}
                    className={cn(
                      'grid cursor-pointer grid-cols-[1rem_1fr] items-center gap-2 px-2.5 py-1.5 text-xs outline-none select-none',
                      'data-highlighted:bg-brand-soft data-highlighted:text-brand',
                      'data-selected:font-medium',
                    )}
                  >
                    <SelectPrimitive.ItemIndicator className="col-start-1 flex justify-center">
                      <CheckIcon className="size-3.5 text-brand" />
                    </SelectPrimitive.ItemIndicator>
                    <SelectPrimitive.ItemText className={cn('col-start-2 truncate', mono && 'font-mono')}>
                      {opt.label}
                    </SelectPrimitive.ItemText>
                  </SelectPrimitive.Item>
                ))
              )}
            </SelectPrimitive.List>
          </SelectPrimitive.Popup>
        </SelectPrimitive.Positioner>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}

/** 下拉多选：勾选切换，触发器展示已选项摘要。 */
export function MultiSelectField({
  values,
  onValuesChange,
  options,
  placeholder = '请选择',
  disabled,
  className,
  'aria-label': ariaLabel,
  emptyText = '暂无选项',
}: {
  values: string[]
  onValuesChange: (values: string[]) => void
  options: SelectOption[]
  placeholder?: string
  disabled?: boolean
  className?: string
  'aria-label'?: string
  emptyText?: string
}) {
  const [open, setOpen] = useState(false)
  const selected = new Set(values)
  const labels = options
    .filter((opt) => selected.has(opt.value))
    .map((opt) => (typeof opt.label === 'string' ? opt.label : opt.value))
  const summary = labels.length === 0
    ? placeholder
    : labels.length <= 2
      ? labels.join('、')
      : `${labels.slice(0, 2).join('、')} 等 ${labels.length} 项`

  const toggle = (value: string) => {
    if (selected.has(value)) {
      onValuesChange(values.filter((v) => v !== value))
    } else {
      onValuesChange([...values, value])
    }
  }

  return (
    <Popover.Root
      open={open}
      modal
      onOpenChange={(next) => {
        if (disabled) return
        setOpen(next)
      }}
    >
      <Popover.Trigger
        disabled={disabled}
        aria-label={ariaLabel}
        className={cn(triggerClass, 'h-9 cursor-pointer', className)}
      >
        <span className={cn('min-w-0 flex-1 truncate', labels.length === 0 && 'text-muted-foreground')}>
          {summary}
        </span>
        <ChevronDownIcon className="size-3.5 shrink-0 text-muted-foreground opacity-70" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner className="z-[70] outline-none" sideOffset={4}>
          <Popover.Popup
            className={cn(
              'surface-panel-solid max-h-[min(16rem,var(--available-height))] min-w-[var(--anchor-width)] origin-[var(--transform-origin)] overflow-hidden rounded-lg border border-border/80 shadow-lg outline-none',
              'transition-[transform,opacity] duration-100 data-starting-style:scale-[0.98] data-starting-style:opacity-0 data-ending-style:scale-[0.98] data-ending-style:opacity-0',
            )}
          >
            <ul className="max-h-[min(16rem,var(--available-height))] overflow-y-auto py-1" role="listbox" aria-multiselectable>
              {options.length === 0 ? (
                <li className="px-3 py-2 text-xs text-muted-foreground">{emptyText}</li>
              ) : (
                options.map((opt) => {
                  const checked = selected.has(opt.value)
                  return (
                    <li key={opt.value} role="option" aria-selected={checked}>
                      <button
                        type="button"
                        className={cn(
                          'grid w-full cursor-pointer grid-cols-[1rem_1fr] items-center gap-2 px-2.5 py-1.5 text-left text-xs outline-none select-none',
                          'hover:bg-brand-soft hover:text-brand',
                          checked && 'font-medium',
                        )}
                        onClick={() => toggle(opt.value)}
                      >
                        <span className="col-start-1 flex justify-center">
                          {checked ? <CheckIcon className="size-3.5 text-brand" /> : null}
                        </span>
                        <span className="col-start-2 min-w-0 truncate">
                          <span className="font-mono text-[11px] text-muted-foreground">{opt.value}</span>
                          {typeof opt.label === 'string' && opt.label !== opt.value ? (
                            <span className="ml-1.5">{opt.label}</span>
                          ) : null}
                        </span>
                      </button>
                    </li>
                  )
                })
              )}
            </ul>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}
