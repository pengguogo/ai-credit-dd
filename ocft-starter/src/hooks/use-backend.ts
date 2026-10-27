import { useEffect, useState } from 'react'

import { api } from '@/lib/api'
import type { HealthReady } from '@/lib/types'

/** 后端就绪状态：如实展示 503 原因，不做假健康。 */
export function useHealth() {
  const [health, setHealth] = useState<HealthReady | null>(null)
  useEffect(() => {
    let alive = true
    const load = () => api.health().then((h) => alive && setHealth(h))
    load()
    const timer = setInterval(load, 30_000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])
  return health
}
