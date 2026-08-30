import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import '../App.css'

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8080'

async function fetchCameraIds(): Promise<string[]> {
  const response = await fetch(`${BACKEND_URL}/streams/`)
  if (!response.ok) {
    throw new Error(`Failed to load cameras: ${response.status}`)
  }
  const ids: string[] = await response.json()
  return ids ?? []
}

function HomePage() {
  const navigate = useNavigate()

  const [cameras, setCameras] = useState<string[]>([])
  const [loadingCameras, setLoadingCameras] = useState(true)
  const [camerasError, setCamerasError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState('')

  useEffect(() => {
    let cancelled = false

    fetchCameraIds()
      .then((ids) => {
        if (cancelled) return
        setCameras(ids)
        setSelectedId((current) => (current && ids.includes(current) ? current : (ids[0] ?? '')))
      })
      .catch((err) => {
        if (cancelled) return
        setCamerasError(err instanceof Error ? err.message : 'Nie udało się pobrać listy kamer')
      })
      .finally(() => {
        if (!cancelled) setLoadingCameras(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const refreshCameras = () => {
    setLoadingCameras(true)
    setCamerasError(null)

    fetchCameraIds()
      .then((ids) => {
        setCameras(ids)
        setSelectedId((current) => (current && ids.includes(current) ? current : (ids[0] ?? '')))
      })
      .catch((err) => {
        setCamerasError(err instanceof Error ? err.message : 'Nie udało się pobrać listy kamer')
      })
      .finally(() => {
        setLoadingCameras(false)
      })
  }

  const handleConnect = () => {
    if (!selectedId) return
    navigate(`/${encodeURIComponent(selectedId)}`)
  }

  return (
    <main className="page">
      <h1 className="title">Select a camera</h1>

      {loadingCameras && <p>Loading cameras…</p>}
      {camerasError && <p className="error">{camerasError}</p>}
      {!loadingCameras && !camerasError && cameras.length === 0 && (
        <p>No cameras are currently streaming.</p>
      )}

      {cameras.length > 0 && (
        <div className="camera-select-row">
          <select
            className="camera-select"
            value={selectedId}
            onChange={(event) => setSelectedId(event.target.value)}
          >
            {cameras.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
          <button type="button" onClick={handleConnect} disabled={!selectedId}>
            Connect
          </button>
        </div>
      )}

      <button type="button" onClick={refreshCameras} disabled={loadingCameras} className="refresh-button">
        Refresh
      </button>
    </main>
  )
}

export default HomePage
