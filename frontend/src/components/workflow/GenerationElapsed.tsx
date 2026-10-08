import { useEffect, useState } from 'react'

import { formatGenerationElapsed } from '@/lib/stepLabels'

type GenerationElapsedProps = {
  startIso: string | null
}

/** Elapsed display ticked every second from server-provided start time. */
export function GenerationElapsed({ startIso }: GenerationElapsedProps) {
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!startIso) return
    const id = window.setInterval(() => setTick((t) => t + 1), 1000)
    return () => window.clearInterval(id)
  }, [startIso])

  if (!startIso) return <span className="tabular-nums">0:00</span>
  return <span className="tabular-nums">{formatGenerationElapsed(startIso)}</span>
}
