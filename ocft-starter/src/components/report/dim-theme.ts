import type { ReportDim, ReportDimSlug } from '@/lib/report-dims'
import type { Variants } from 'motion/react'

export const THEME_CLASS: Record<ReportDim['theme'], {
  glow: string
  ring: string
  chip: string
  soft: string
  bar: string
}> = {
  teal: {
    glow: 'from-tech/25 via-transparent to-brand/10',
    ring: 'stroke-tech',
    chip: 'border-tech/35 bg-tech-soft/80 text-tech',
    soft: 'bg-tech-soft/50',
    bar: 'bg-tech',
  },
  sky: {
    glow: 'from-info/25 via-transparent to-tech/10',
    ring: 'stroke-info',
    chip: 'border-info/35 bg-info/10 text-info',
    soft: 'bg-info/5',
    bar: 'bg-info',
  },
  amber: {
    glow: 'from-warning/25 via-transparent to-brand/10',
    ring: 'stroke-warning',
    chip: 'border-warning/35 bg-warning/10 text-warning',
    soft: 'bg-warning/5',
    bar: 'bg-warning',
  },
  rose: {
    glow: 'from-destructive/20 via-transparent to-brand/10',
    ring: 'stroke-destructive',
    chip: 'border-destructive/30 bg-destructive/10 text-destructive',
    soft: 'bg-destructive/5',
    bar: 'bg-destructive',
  },
  orange: {
    glow: 'from-brand/30 via-transparent to-tech/10',
    ring: 'stroke-brand',
    chip: 'border-brand/40 bg-brand-soft text-brand',
    soft: 'bg-brand-soft/60',
    bar: 'bg-brand',
  },
}

export const rise: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } },
}

export const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
}

export type DimIconSlug = ReportDimSlug
