/**
 * 尽调维度页共用视觉：入场、计数、环形分、主题色。
 * 动画只装饰真实数据，不补造结论。
 */
import {
  Building2Icon,
  FileTextIcon,
  LandmarkIcon,
  RadarIcon,
  ShieldAlertIcon,
  WalletCardsIcon,
} from 'lucide-react'
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react'
import { useEffect, type ReactNode } from 'react'

import { rise, stagger, THEME_CLASS } from '@/components/report/dim-theme'
import type { ReportDim, ReportDimSlug } from '@/lib/report-dims'
import { cn } from '@/lib/utils'

export function DimGlyph({ slug, className }: { slug: ReportDimSlug; className?: string }) {
  const Icon = {
    business: Building2Icon,
    finance: LandmarkIcon,
    opinion: RadarIcon,
    fraud: ShieldAlertIcon,
    'credit-risk': WalletCardsIcon,
    report: FileTextIcon,
  }[slug]
  return <Icon className={className} aria-hidden />
}

export function Rise({ children, className, delay = 0 }: {
  children: ReactNode
  className?: string
  delay?: number
}) {
  const reduce = useReducedMotion()
  if (reduce) return <div className={className}>{children}</div>
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}

export function Stagger({ children, className }: { children: ReactNode; className?: string }) {
  const reduce = useReducedMotion()
  if (reduce) return <div className={className}>{children}</div>
  return (
    <motion.div className={className} variants={stagger} initial="hidden" animate="show">
      {children}
    </motion.div>
  )
}

export function StaggerItem({ children, className }: { children: ReactNode; className?: string }) {
  const reduce = useReducedMotion()
  if (reduce) return <div className={className}>{children}</div>
  return (
    <motion.div className={className} variants={rise}>
      {children}
    </motion.div>
  )
}

/** 数字缓动到目标值（展示用，不改业务数据）。 */
export function CountUp({ value, digits = 0, className }: {
  value: number
  digits?: number
  className?: string
}) {
  const reduce = useReducedMotion()
  const motionValue = useMotionValue(reduce ? value : 0)
  const spring = useSpring(motionValue, { stiffness: 90, damping: 22 })
  const display = useTransform(spring, (v) =>
    v.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits }))

  useEffect(() => {
    motionValue.set(reduce ? value : 0)
    const id = window.requestAnimationFrame(() => motionValue.set(value))
    return () => window.cancelAnimationFrame(id)
  }, [motionValue, reduce, value])

  if (reduce) {
    return (
      <span className={className}>
        {value.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })}
      </span>
    )
  }
  return <motion.span className={className}>{display}</motion.span>
}

export function ScoreRing({ score, max = 100, label, tone = 'orange', size = 112 }: {
  score: number
  max?: number
  label: string
  tone?: ReportDim['theme']
  size?: number
}) {
  const reduce = useReducedMotion()
  const theme = THEME_CLASS[tone]
  const r = 42
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(1, max === 0 ? 0 : score / max))
  const offset = c * (1 - pct)

  return (
    <div className="relative inline-flex flex-col items-center" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" className="size-full -rotate-90" aria-hidden>
        <circle cx="50" cy="50" r={r} fill="none" stroke="currentColor" strokeWidth="8" className="text-muted/60" />
        <motion.circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          className={theme.ring}
          strokeDasharray={c}
          initial={reduce ? false : { strokeDashoffset: c }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <CountUp value={score} digits={score % 1 === 0 ? 0 : 1} className="text-2xl font-semibold tracking-tight" />
        <span className="text-[10px] text-muted-foreground">{label}</span>
      </div>
    </div>
  )
}

export function MetricTile({ label, value, hint, tone = 'orange', className }: {
  label: string
  value: ReactNode
  hint?: string
  tone?: ReportDim['theme']
  className?: string
}) {
  const theme = THEME_CLASS[tone]
  return (
    <StaggerItem
      className={cn(
        'relative overflow-hidden rounded-xl border border-border/70 bg-card/80 px-3.5 py-3 shadow-[inset_0_1px_0_rgb(255_255_255/0.5)]',
        className,
      )}
    >
      <span aria-hidden className={cn('absolute inset-x-0 top-0 h-0.5', theme.bar)} />
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <div className="mt-1 truncate text-base font-semibold tracking-tight">{value}</div>
      {hint ? <p className="mt-0.5 text-[10px] text-muted-foreground">{hint}</p> : null}
    </StaggerItem>
  )
}

export function DimStepRail({ dims, active, onSelect }: {
  dims: ReportDim[]
  active: ReportDimSlug
  onSelect: (slug: ReportDimSlug) => void
}) {
  const reduce = useReducedMotion()
  return (
    <ol className="flex flex-wrap items-center gap-1.5" aria-label="尽调维度">
      {dims.map((d, i) => {
        const on = d.slug === active
        const theme = THEME_CLASS[d.theme]
        return (
          <li key={d.slug} className="flex items-center gap-1.5">
            {i > 0 && (
              <span aria-hidden className="hidden h-px w-4 bg-border sm:block" />
            )}
            <motion.button
              type="button"
              onClick={() => onSelect(d.slug)}
              whileHover={reduce ? undefined : { y: -2 }}
              whileTap={reduce ? undefined : { scale: 0.98 }}
              className={cn(
                'inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
                on ? theme.chip : 'border-border/70 bg-card/70 text-muted-foreground hover:bg-muted',
              )}
              aria-current={on ? 'step' : undefined}
            >
              <DimGlyph slug={d.slug} className="size-3.5" />
              <span className="font-mono text-[10px] opacity-70">{d.step}</span>
              <span>{d.label}</span>
            </motion.button>
          </li>
        )
      })}
    </ol>
  )
}
