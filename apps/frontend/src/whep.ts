import {
  DETECTIONS_CHANNEL_LABEL,
  parseDetectionFrame,
  type DetectionFrame,
} from './detections'

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
  /** Called for each valid detection frame. Ignored when detections are off. */
  onDetections?: (frame: DetectionFrame) => void
}

export interface WhepOptions {
  /**
   * Subscribe to the detections data channel. Defaults to true.
   *
   * Set false for a video-only consumer: the SDP then carries no
   * `m=application` section and no detection metadata is delivered.
   */
  detections?: boolean
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

  static async connect(
    backendUrl: string,
    streamId: string,
    stunUrl: string,
    handlers: WhepHandlers = {},
    options: WhepOptions = {},
  ): Promise<WhepSession> {
    const wantsDetections = options.detections ?? true

    const pc = new RTCPeerConnection({ iceServers: [{ urls: stunUrl }] })
    pc.addTransceiver('video', { direction: 'recvonly' })

    if (wantsDetections) {
      // Created before the offer: a data channel only negotiates if the
      // *offering* side declares an m=application section. The relay answers,
      // so a channel created there would never open.
      //
      // Unordered with no retransmits -- a detection that arrives late has
      // already been superseded by a newer frame.
      const channel = pc.createDataChannel(DETECTIONS_CHANNEL_LABEL, {
        ordered: false,
        maxRetransmits: 0,
      })

      // Payloads arrive as ArrayBuffer when the publisher sends bytes (the
      // Python client does) and as a string when it sends text. Decode both:
      // the wire format is UTF-8 JSON either way.
      channel.binaryType = 'arraybuffer'
      const decoder = new TextDecoder()

      channel.addEventListener('message', (event: MessageEvent<string | ArrayBuffer>) => {
        const text =
          typeof event.data === 'string' ? event.data : decoder.decode(event.data)

        const frame = parseDetectionFrame(text)
        // A single malformed frame must not break the stream.
        if (frame) handlers.onDetections?.(frame)
      })
    }

    pc.addEventListener('track', (event) => {
      handlers.onTrack?.(event.streams[0] ?? new MediaStream([event.track]))
    })
    pc.addEventListener('connectionstatechange', () =>
      handlers.onConnectionStateChange?.(pc.connectionState),
    )

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
