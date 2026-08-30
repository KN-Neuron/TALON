import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import '../App.css'
import NotFoundPage from './NotFoundPage'
import { WhepError, WhepSession } from '../whep'

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8080'
const STUN_URL = import.meta.env.VITE_STUN_URL ?? 'stun:stun.l.google.com:19302'

function StreamPage() {
  const { id } = useParams<{ id: string }>()
  return <StreamPageView key={id} id={id} />
}

function StreamPageView({ id }: { id?: string }) {
  const navigate = useNavigate()

  const videoRef = useRef<HTMLVideoElement>(null)
  const sessionRef = useRef<WhepSession | null>(null)

  const [connecting, setConnecting] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (!id) return

    let cancelled = false

    WhepSession.connect(BACKEND_URL, id, STUN_URL, {
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
    })
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
  }, [id, navigate])

  const disconnect = () => {
    sessionRef.current?.close()
    sessionRef.current = null
    navigate('/')
  }

  if (notFound && id) {
    return <NotFoundPage id={id} />
  }

  return (
    <main className="stream-page">
      <video ref={videoRef} autoPlay playsInline muted className="fullscreen-video" />
      {connecting && <p className="connecting-label">Connecting…</p>}
      {error && <p className="connecting-label error">{error}</p>}
      <button type="button" onClick={disconnect} className="disconnect-button">
        Disconnect
      </button>
    </main>
  )
}

export default StreamPage
