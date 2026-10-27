/**
 * 会话恢复时的二次元风格加载屏：不展示「正在恢复登录态」文案，只靠动画表达。
 */
import { motion, useReducedMotion } from 'motion/react'

import brandLogo from '@/assets/logo-orange.svg'

export function BootSplash() {
  const reduce = useReducedMotion()

  return (
    <div
      className="relative flex h-full items-center justify-center overflow-hidden bg-[#070b14]"
      role="status"
      aria-live="polite"
      aria-label="加载中"
    >
      {/* 背景光晕 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 60% 45% at 50% 40%, rgba(233,85,4,0.22), transparent 55%),'
            + 'radial-gradient(ellipse 50% 40% at 20% 80%, rgba(56,189,248,0.12), transparent 50%),'
            + 'radial-gradient(ellipse 40% 35% at 85% 20%, rgba(217,70,239,0.14), transparent 45%)',
        }}
      />

      {/* 速度线 */}
      {!reduce && (
        <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden opacity-40">
          {Array.from({ length: 12 }, (_, i) => (
            <span
              key={i}
              className="absolute h-px bg-gradient-to-r from-transparent via-cyan-300/70 to-transparent"
              style={{
                top: `${8 + i * 7.5}%`,
                left: '-20%',
                width: '60%',
                animation: `boot-speed ${1.1 + (i % 4) * 0.18}s linear infinite`,
                animationDelay: `${i * 0.08}s`,
                transform: `rotate(${-8 + (i % 3) * 2}deg)`,
              }}
            />
          ))}
        </div>
      )}

      <div className="relative z-10 flex flex-col items-center gap-6">
        {/* 魔法阵 + Logo */}
        <div className="relative flex size-36 items-center justify-center sm:size-44">
          <motion.div
            aria-hidden
            className="absolute inset-0 rounded-full border border-brand/50"
            animate={reduce ? undefined : { rotate: 360 }}
            transition={{ duration: 8, repeat: Infinity, ease: 'linear' }}
            style={{
              boxShadow: '0 0 24px rgba(233,85,4,0.25), inset 0 0 18px rgba(233,85,4,0.12)',
            }}
          />
          <motion.div
            aria-hidden
            className="absolute inset-3 rounded-full border border-dashed border-cyan-300/40"
            animate={reduce ? undefined : { rotate: -360 }}
            transition={{ duration: 5.5, repeat: Infinity, ease: 'linear' }}
          />
          <motion.div
            aria-hidden
            className="absolute inset-6 rounded-full border border-fuchsia-400/35"
            animate={reduce ? undefined : { scale: [0.92, 1.05, 0.92], opacity: [0.55, 1, 0.55] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
          />

          {/* 轨道光点 */}
          {!reduce && (
            <motion.div
              aria-hidden
              className="absolute inset-0"
              animate={{ rotate: 360 }}
              transition={{ duration: 3.2, repeat: Infinity, ease: 'linear' }}
            >
              <span className="absolute left-1/2 top-0 size-2 -translate-x-1/2 rounded-full bg-brand shadow-[0_0_10px_rgba(233,85,4,0.9)]" />
              <span className="absolute bottom-0 left-1/2 size-1.5 -translate-x-1/2 rounded-full bg-cyan-300 shadow-[0_0_8px_rgba(103,232,249,0.8)]" />
            </motion.div>
          )}

          <motion.img
            src={brandLogo}
            alt=""
            className="relative z-10 h-10 w-auto drop-shadow-[0_0_16px_rgba(233,85,4,0.55)] sm:h-12"
            animate={reduce ? undefined : { y: [0, -6, 0] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
          />
        </div>

        {/* 跳动的二次元加载点 */}
        <div className="flex items-end gap-2" aria-hidden>
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="block size-2.5 rounded-full bg-gradient-to-br from-brand to-fuchsia-400"
              animate={reduce ? undefined : { y: [0, -10, 0], scale: [1, 1.25, 1] }}
              transition={{
                duration: 0.7,
                repeat: Infinity,
                ease: 'easeInOut',
                delay: i * 0.14,
              }}
            />
          ))}
        </div>

        {/* 飘散粒子 */}
        {!reduce && (
          <div aria-hidden className="pointer-events-none absolute inset-x-0 top-1/3 h-48">
            {Array.from({ length: 8 }, (_, i) => (
              <motion.span
                key={i}
                className="absolute size-1.5 rounded-full bg-cyan-200/80"
                style={{ left: `${18 + i * 9}%` }}
                animate={{
                  y: [40, -80],
                  opacity: [0, 1, 0],
                  x: [0, (i % 2 === 0 ? 12 : -12)],
                }}
                transition={{
                  duration: 2.4 + (i % 3) * 0.4,
                  repeat: Infinity,
                  delay: i * 0.22,
                  ease: 'easeOut',
                }}
              />
            ))}
          </div>
        )}
      </div>

      <style>{`
        @keyframes boot-speed {
          from { transform: translateX(0); opacity: 0; }
          15% { opacity: 0.9; }
          to { transform: translateX(160vw); opacity: 0; }
        }
      `}</style>
    </div>
  )
}
