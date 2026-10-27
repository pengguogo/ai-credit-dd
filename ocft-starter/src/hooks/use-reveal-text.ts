/**
 * 把已到手的完整文本按段落节奏「吐」出来，用于 run 结束后的答案展示。
 * 按块更新而不是逐字，避免 Markdown 每帧重解析把页面拖死。
 */
import { useEffect, useState } from 'react'

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** 按空行切块；没有空行时按行，保证至少能渐进显示。 */
function splitChunks(fullText: string): string[] {
  const parts = fullText.split(/\n{2,}/).filter((p) => p.length > 0)
  if (parts.length >= 2) return parts
  const lines = fullText.split('\n')
  if (lines.length <= 1) return [fullText]
  const chunks: string[] = []
  for (let i = 0; i < lines.length; i += 3) {
    chunks.push(lines.slice(i, i + 3).join('\n'))
  }
  return chunks
}

export function useRevealText(fullText: string, enabled: boolean): {
  text: string
  done: boolean
} {
  const source = typeof fullText === 'string' ? fullText : String(fullText ?? '')
  const animate = enabled && !!source && !prefersReducedMotion()
  const chunks = animate ? splitChunks(source) : [source]
  const [visibleCount, setVisibleCount] = useState(() => (animate ? 1 : chunks.length))

  useEffect(() => {
    if (!animate || chunks.length <= 1) return
    let index = 1
    const id = window.setInterval(() => {
      index += 1
      setVisibleCount(index)
      if (index >= chunks.length) window.clearInterval(id)
    }, 160)
    return () => window.clearInterval(id)
  }, [animate, source]) // eslint-disable-line react-hooks/exhaustive-deps -- chunks 由 source 派生

  const count = animate ? Math.min(visibleCount, chunks.length) : chunks.length
  const text = chunks.slice(0, count).join('\n\n')
  return { text, done: !animate || count >= chunks.length }
}
