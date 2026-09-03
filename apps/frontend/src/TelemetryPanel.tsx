import { useEffect, useState } from 'react'
import type { DetectionFrame } from './detections'

const LATENCY_REFRESH_MS = 500
/** Beyond this the producer and browser clocks clearly disagree. */
const MAX_PLAUSIBLE_LATENCY_MS = 60_000

interface Props {
  frame: DetectionFrame | null
}

/**
 * Shows the health of the detection feed.
 *
 * Latency is measured against the producer's wall clock, so it is only
 * meaningful when the producer and the browser have roughly synchronised
 * clocks. It is useful for spotting a stalled feed regardless.
 */
function TelemetryPanel({ frame }: Props) {
  // Sampled on a timer rather than during render: reading the clock while
  // rendering is impure and would not refresh on its own between frames. The
  // first sample is taken by the initialiser so the effect only schedules
  // subsequent ones.
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), LATENCY_REFRESH_MS)
    return () => clearInterval(timer)
  }, [])

  const latencyMs = frame ? now - frame.timestamp_ms : null

  if (!frame) {
    return (
      <aside className="telemetry-panel">
        <span className="telemetry-idle">Waiting for detections…</span>
      </aside>
    )
  }

  const fps = frame.frame_interval_s > 0 ? 1 / frame.frame_interval_s : 0
  const latencyLabel =
    latencyMs !== null && latencyMs >= 0 && latencyMs < MAX_PLAUSIBLE_LATENCY_MS
      ? `${latencyMs} ms`
      : '—'

  return (
    <aside className="telemetry-panel">
      <span><strong>{frame.objects.length}</strong> objects</span>
      <span>{fps.toFixed(0)} fps</span>
      <span>frame {frame.frame_id}</span>
      <span>{latencyLabel}</span>
    </aside>
  )
}

export default TelemetryPanel
