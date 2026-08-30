const ICE_GATHERING_TIMEOUT_MS = 3000

async function waitForIceGathering(pc: RTCPeerConnection): Promise<void> {
  if (pc.iceGatheringState === 'complete') return
  await new Promise<void>((resolve) => {
    const timeout = setTimeout(resolve, ICE_GATHERING_TIMEOUT_MS)
    pc.addEventListener('icegatheringstatechange', () => {
      if (pc.iceGatheringState === 'complete') {
        clearTimeout(timeout)
        resolve()
      }
    })
  })
}

export interface WhepHandlers {
  onTrack?: (stream: MediaStream) => void
  onConnectionStateChange?: (state: RTCPeerConnectionState) => void
}

export class WhepError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'WhepError'
    this.status = status
  }
}

export class WhepSession {
  private readonly pc: RTCPeerConnection
  private readonly resourceUrl: string

  private constructor(pc: RTCPeerConnection, resourceUrl: string) {
    this.pc = pc
    this.resourceUrl = resourceUrl
  }

  static async connect(backendUrl: string, streamId: string, stunUrl: string, handlers: WhepHandlers = {}): Promise<WhepSession> {
    const pc = new RTCPeerConnection({ iceServers: [{ urls: stunUrl }] })
    pc.addTransceiver('video', { direction: 'recvonly' })

    pc.addEventListener('track', (event) => {
      handlers.onTrack?.(event.streams[0] ?? new MediaStream([event.track]))
    })
    pc.addEventListener('connectionstatechange', () => handlers.onConnectionStateChange?.(pc.connectionState))

    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    await waitForIceGathering(pc)

    const response = await fetch(`${backendUrl}/whep/${streamId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/sdp' },
      body: pc.localDescription?.sdp,
    })

    if (!response.ok) {
      pc.close()
      throw new WhepError(response.status, `WHEP subscribe failed: ${response.status} ${await response.text()}`)
    }

    const location = response.headers.get('Location')
    const resourceUrl = location ? new URL(location, backendUrl).toString() : `${backendUrl}/whep/${streamId}`

    const answer = await response.text()
    await pc.setRemoteDescription({ type: 'answer', sdp: answer })

    return new WhepSession(pc, resourceUrl)
  }

  async close(): Promise<void> {
    this.pc.close()
    try {
      await fetch(this.resourceUrl, { method: 'DELETE' })
    } catch {}
  }
}
