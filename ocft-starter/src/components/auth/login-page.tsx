/**
 * 登录页：深色几何轨道 + 平安橙高亮，品牌级第一屏。
 * 左侧六角色流程图：1–3 并行 → 4 → 5 → 6，循环动画。
 */
import { ArrowRightIcon, EyeIcon, EyeOffIcon, LockIcon, UserIcon } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useId, useRef, useState } from 'react'

import brandLogo from '@/assets/logo-orange.svg'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { ApiError } from '@/lib/api'
import { DD_ROLES } from '@/lib/format'
import { cn } from '@/lib/utils'

/** 动画阶段：0=并行1–3，1=反欺诈，2=评级，3=报告 */
const FLOW_PHASES = [
  { active: new Set([0, 1, 2]), label: '并行取证' },
  { active: new Set([3]), label: '反欺诈' },
  { active: new Set([4]), label: '评级授信' },
  { active: new Set([5]), label: '报告成文' },
] as const

function RoleFlowChart() {
  const reduce = useReducedMotion()
  const [phase, setPhase] = useState(0)

  useEffect(() => {
    if (reduce) return
    const id = window.setInterval(() => {
      setPhase((p) => (p + 1) % FLOW_PHASES.length)
    }, 1600)
    return () => window.clearInterval(id)
  }, [reduce])

  const active = FLOW_PHASES[phase].active
  const parallel = DD_ROLES.slice(0, 3)
  const sequential = DD_ROLES.slice(3)

  return (
    <div className="w-full max-w-xl" aria-label="六角色 Agent 调度流程">
      <motion.div
        className="mx-auto w-fit rounded-lg border border-brand/40 bg-brand/10 px-4 py-1.5 font-mono text-xs text-brand"
        animate={reduce ? undefined : { opacity: [0.75, 1, 0.75] }}
        transition={{ duration: 2.4, repeat: Infinity }}
        title={FLOW_PHASES[phase].label}
      >
        主控 Agent
      </motion.div>
      <FlowArrow active={!reduce} />

      <div>
        <p className="mb-2 text-center font-mono text-[10px] text-slate-500">并行</p>
        <ul className="grid grid-cols-3 gap-3">
          {parallel.map((role, i) => (
            <RoleNode
              key={role.role}
              index={i}
              name={role.name}
              active={reduce || active.has(i)}
              reduce={!!reduce}
            />
          ))}
        </ul>
        <div
          aria-hidden
          className={cn(
            'mx-auto mt-2 h-4 w-[70%] rounded-b-xl border-x border-b border-white/15',
            !reduce && phase === 0 && 'border-brand/45',
          )}
        />
      </div>

      <FlowArrow active={!reduce && phase >= 1} />

      <p className="mb-2 text-center font-mono text-[10px] text-slate-500">串行</p>
      <ul className="mx-auto flex w-full max-w-sm flex-col items-stretch">
        {sequential.map((role, i) => {
          const index = i + 3
          return (
            <li key={role.role} className="flex flex-col items-center">
              {i > 0 && <FlowArrow active={!reduce && phase >= i + 1} />}
              <RoleNode
                index={index}
                name={role.name}
                active={reduce || active.has(index)}
                reduce={!!reduce}
                wide
              />
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function RoleNode({ index, name, active, reduce, wide }: {
  index: number
  name: string
  active: boolean
  reduce: boolean
  wide?: boolean
}) {
  return (
    <motion.div
      layout={false}
      className={cn(
        'rounded-xl border px-3 py-3 font-mono text-xs transition-colors',
        wide ? 'w-full text-center' : 'text-center',
        active
          ? 'border-brand/70 bg-brand/15 text-white shadow-[0_0_24px_rgba(255,102,0,0.16)]'
          : 'border-white/10 bg-white/[0.04] text-slate-400',
      )}
      animate={reduce || !active ? { scale: 1 } : { scale: [1, 1.02, 1] }}
      transition={{ duration: 0.9, repeat: active && !reduce ? Infinity : 0 }}
    >
      <p className={cn('text-[10px]', active ? 'text-brand' : 'text-slate-500')}>
        {String(index + 1).padStart(2, '0')}
      </p>
      <p className="mt-1 font-medium tracking-wide text-current">{name}</p>
    </motion.div>
  )
}

function FlowArrow({ active }: { active: boolean }) {
  return (
    <div
      aria-hidden
      className={cn(
        'relative mx-auto my-1 flex h-6 w-px justify-center overflow-hidden bg-white/15',
        active && 'bg-brand/35',
      )}
    >
      <span
        className={cn(
          'absolute inset-x-0 top-0 h-1/2 bg-gradient-to-b from-transparent to-brand',
          active ? 'animate-[flow-dash_1.2s_linear_infinite]' : 'opacity-0',
        )}
      />
    </div>
  )
}

export function LoginPage({ onLogin }: {
  onLogin: (username: string, password: string) => Promise<void>
}) {
  const userId = useId()
  const passId = useId()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    let raf = 0
    const nodes = Array.from({ length: 48 }, () => ({
      x: Math.random(),
      y: Math.random(),
      vx: (Math.random() - 0.5) * 0.00035,
      vy: (Math.random() - 0.5) * 0.00035,
    }))

    const resize = () => {
      canvas.width = window.innerWidth * devicePixelRatio
      canvas.height = window.innerHeight * devicePixelRatio
      canvas.style.width = `${window.innerWidth}px`
      canvas.style.height = `${window.innerHeight}px`
      ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)

    const tick = () => {
      const width = window.innerWidth
      const height = window.innerHeight
      ctx.clearRect(0, 0, width, height)

      // 扫描线网格
      ctx.strokeStyle = 'rgba(255,102,0,0.08)'
      ctx.lineWidth = 1
      const gap = 48
      for (let x = 0; x < width; x += gap) {
        ctx.beginPath()
        ctx.moveTo(x, 0)
        ctx.lineTo(x, height)
        ctx.stroke()
      }
      for (let y = 0; y < height; y += gap) {
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(width, y)
        ctx.stroke()
      }

      for (const n of nodes) {
        n.x += n.vx
        n.y += n.vy
        if (n.x < 0 || n.x > 1) n.vx *= -1
        if (n.y < 0 || n.y > 1) n.vy *= -1
      }

      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i]
          const b = nodes[j]
          const dx = (a.x - b.x) * width
          const dy = (a.y - b.y) * height
          const dist = Math.hypot(dx, dy)
          if (dist < 160) {
            ctx.strokeStyle = `rgba(255,102,0,${0.18 * (1 - dist / 160)})`
            ctx.beginPath()
            ctx.moveTo(a.x * width, a.y * height)
            ctx.lineTo(b.x * width, b.y * height)
            ctx.stroke()
          }
        }
      }

      for (const n of nodes) {
        ctx.fillStyle = '#ff6600'
        ctx.beginPath()
        ctx.arc(n.x * width, n.y * height, 1.6, 0, Math.PI * 2)
        ctx.fill()
      }

      // 旋转轨道
      const t = performance.now() / 1000
      const cx = width * 0.72
      const cy = height * 0.42
      ctx.save()
      ctx.translate(cx, cy)
      ctx.rotate(t * 0.18)
      for (let i = 0; i < 3; i++) {
        const r = 90 + i * 48
        ctx.strokeStyle = `rgba(255,102,0,${0.22 - i * 0.05})`
        ctx.lineWidth = 1.2
        ctx.setLineDash([8, 14])
        ctx.beginPath()
        ctx.arc(0, 0, r, 0, Math.PI * 2)
        ctx.stroke()
        ctx.setLineDash([])
        const ang = t * (0.6 + i * 0.2)
        ctx.fillStyle = '#ff6600'
        ctx.beginPath()
        ctx.arc(Math.cos(ang) * r, Math.sin(ang) * r, 3, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.restore()

      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await onLogin(username.trim(), password)
    } catch (exc: unknown) {
      setError(exc instanceof ApiError ? exc.message : '登录失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative flex min-h-full overflow-hidden bg-[#0a0f1a] text-slate-100">
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0" aria-hidden />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 55% 50% at 18% 40%, rgba(255,102,0,0.22), transparent 60%),'
            + 'radial-gradient(ellipse 40% 35% at 80% 70%, rgba(255,102,0,0.1), transparent 55%),'
            + 'linear-gradient(180deg, rgba(10,15,26,0.2), rgba(10,15,26,0.85))',
        }}
      />

      <div className="relative z-10 mx-auto flex w-full max-w-7xl flex-1 flex-col px-6 py-6 lg:px-10 lg:py-8">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4 animate-[login-rise_0.7s_ease-out]">
          <img src={brandLogo} alt="金融壹账通" className="h-8 w-auto" />
          <h1 className="ml-auto text-right text-base font-semibold tracking-tight text-white sm:text-lg">
            企业智能信贷尽调
            <span className="mx-2 text-slate-600" aria-hidden>·</span>
            <span className="text-brand">可信取证 · 实时调度</span>
          </h1>
        </header>

        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-12 lg:flex-row lg:items-center lg:gap-16 xl:gap-24">
        <section className="flex min-w-0 w-full flex-1 justify-center animate-[login-rise_0.8s_ease-out] lg:justify-end lg:pr-4">
          <RoleFlowChart />
        </section>

        <form
          onSubmit={(e) => void submit(e)}
          className="w-full max-w-md shrink-0 animate-[login-rise_0.9s_ease-out] rounded-2xl border border-white/10 bg-[#121a2b]/72 p-6 shadow-[0_24px_80px_rgba(0,0,0,0.45)] backdrop-blur-xl sm:p-8 lg:flex-none"
        >
          <p className="font-mono text-[11px] tracking-[0.25em] text-brand uppercase">Sign in</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">进入智能尽调</h2>
          <p className="mt-1 text-xs text-slate-400">演示账号见表单下方提示</p>

          <div className="mt-6 space-y-4">
            <div>
              <label htmlFor={userId} className="text-xs text-slate-400">用户名</label>
              <div className="relative mt-1">
                <UserIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-500" />
                <Input
                  id={userId}
                  value={username}
                  autoComplete="username"
                  onChange={(e) => setUsername(e.target.value)}
                  className="h-11 border-white/15 bg-[#0a0f1a]/80 pl-10 text-slate-100 placeholder:text-slate-600"
                  placeholder="admin"
                />
              </div>
            </div>
            <div>
              <label htmlFor={passId} className="text-xs text-slate-400">密码</label>
              <div className="relative mt-1">
                <LockIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-500" />
                <Input
                  id={passId}
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  autoComplete="current-password"
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-11 border-white/15 bg-[#0a0f1a]/80 pr-11 pl-10 text-slate-100 placeholder:text-slate-600"
                  placeholder="输入密码"
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 flex w-11 cursor-pointer items-center justify-center text-slate-500 hover:text-slate-200"
                  aria-label={showPassword ? '隐藏密码' : '显示密码'}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((v) => !v)}
                >
                  {showPassword ? <EyeOffIcon className="size-4" /> : <EyeIcon className="size-4" />}
                </button>
              </div>
            </div>
          </div>

          {error && (
            <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>
          )}

          <Button
            type="submit"
            size="lg"
            disabled={busy || !username.trim() || !password}
            className="mt-6 h-11 w-full cursor-pointer bg-brand text-white hover:bg-brand/90"
          >
            {busy ? <Spinner /> : <ArrowRightIcon />}
            {busy ? '正在验证…' : '登录'}
          </Button>

          <div className="mt-5 rounded-lg border border-brand/25 bg-brand/5 px-3 py-2.5 font-mono text-[11px] leading-relaxed text-slate-400">
            <p className="text-brand">演示账号（推荐 admin）</p>
            <p className="mt-1">admin / Admin@123 · 全部权限（含审批）</p>
            <p>account_manager / Demo@123 · 客户经理（无系统管理）</p>
            <p>viewer / View@123 · 只读：智能尽调 + 尽调1–5步</p>
          </div>
        </form>
        </div>
      </div>

      <style>{`
        @keyframes login-rise {
          from { opacity: 0; transform: translateY(18px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes flow-dash {
          from { transform: translateY(-100%); }
          to { transform: translateY(200%); }
        }
      `}</style>
    </div>
  )
}
