import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import '../App.css'
import NotFoundPage from './NotFoundPage'
import DetectionOverlay from '../DetectionOverlay'
import TelemetryPanel from '../TelemetryPanel'
import type { DetectionFrame } from '../detections'
import { WhepError, WhepSession } from '../whep'

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8080'
const STUN_URL = import.meta.env.VITE_STUN_URL ?? 'stun:stun.l.google.com:19302'

function StreamPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams] = useSearchParams()
  // `?raw=1` subscribes to video only, skipping the detections channel.
  const raw = searchParams.get('raw') === '1'
  return <StreamPageView key={`${id}:${raw}`} id={id} raw={raw} />
}

function StreamPageView({ id, raw }: { id?: string; raw: boolean }) {
  const navigate = useNavigate()

  const videoRef = useRef<HTMLVideoElement>(null)
  const sessionRef = useRef<WhepSession | null>(null)

  const [connecting, setConnecting] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [frame, setFrame] = useState<DetectionFrame | null>(null)

  // Only the newest frame matters, so replace rather than accumulate.
  const handleDetections = useCallback((incoming: DetectionFrame) => {
    setFrame((current) =>
      // Guard against reordering: the channel is unordered by design.
      current && incoming.frame_id < current.frame_id ? current : incoming,
    )
  }, [])

  useEffect(() => {
    if (!id) return

    let cancelled = false

    WhepSession.connect(
      BACKEND_URL,
      id,
      STUN_URL,
      {
        onTrack: (stream) => {
          if (cancelled) return
          if (videoRef.current) {
            videoRef.current.srcObject = stream
          }
        },
        onConnectionStateChange: (state) => {
          if (state === 'failed' || state === 'closed' || state === 'disconnected') {
            if (!cancelled) navigate('/')
          }
        },
        onDetections: raw ? undefined : handleDetections,
      },
      { detections: !raw },
    )
      .then((session) => {
        if (cancelled) {
          session.close()
          return
        }
        sessionRef.current = session
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof WhepError && err.status === 404) {
          setNotFound(true)
        } else {
          setError(err instanceof Error ? err.message : 'Nie udało się połączyć ze strumieniem')
        }
      })
      .finally(() => {
        if (!cancelled) setConnecting(false)
      })

    return () => {
      cancelled = true
      sessionRef.current?.close()
      sessionRef.current = null
    }
  }, [id, navigate, raw, handleDetections])

  const disconnect = () => {
    sessionRef.current?.close()
    sessionRef.current = null
    navigate('/')
  }

  const toggleRaw = () => {
    if (!id) return
    navigate(raw ? `/${encodeURIComponent(id)}` : `/${encodeURIComponent(id)}?raw=1`)
  }

  if (notFound && id) {
    return <NotFoundPage id={id} />
  }

  return (
    <main className="stream-page">
      <div className="video-stage">
        <video ref={videoRef} autoPlay playsInline muted className="fullscreen-video" />
        {!raw && <DetectionOverlay frame={frame} videoRef={videoRef} />}
      </div>

      {connecting && <p className="connecting-label">Connecting…</p>}
      {error && <p className="connecting-label error">{error}</p>}

      {!raw && <TelemetryPanel frame={frame} />}

      <div className="stream-controls">
        <button type="button" onClick={toggleRaw} className="mode-button">
          {raw ? 'Show detections' : 'Raw video'}
        </button>
        <button type="button" onClick={disconnect} className="disconnect-button">
          Disconnect
        </button>
      </div>
    </main>
  )
}

export default StreamPage
