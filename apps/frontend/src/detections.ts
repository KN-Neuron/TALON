/**
 * Detection frames received over the `detections` data channel.
 *
 * See docs/detection-protocol.md for the wire format. The relay forwards these
 * bytes without parsing them, so this file is the only place the browser needs
 * to know the schema.
 */

export const DETECTIONS_CHANNEL_LABEL = 'detections'
export const SUPPORTED_SCHEMA_VERSION = 1

export interface BoundingBox {
  /** Distance in pixels from the left edge of the source frame. */
  left: number
  /** Distance in pixels from the top edge of the source frame. */
  top: number
  width: number
  height: number
}

export interface Position {
  /** Sideways offset in metres; negative is left of centre. */
  lateral_m: number
  /** Distance ahead of the drone in metres. */
  forward_m: number
}

export interface DetectedObject {
  /** Stable across frames for the same physical object. */
  track_id: number
  class_id: number
  class_name: string
  /** 0.0 to 1.0. */
  confidence: number
  box: BoundingBox
  position?: Position
  /** Rate of change of position.forward_m; negative means approaching. */
  closing_speed_mps?: number
  /** Seconds until impact at the current closing speed. */
  time_to_collision_s?: number
  /** 0 when detected this frame; grows while the tracker coasts. */
  frames_since_seen: number
}

export interface DetectionFrame {
  version: number
  frame_id: number
  /** Producer wall clock. Not synchronised with the video timeline. */
  timestamp_ms: number
  frame_interval_s: number
  /** Width of the frame the boxes were computed on. */
  image_width: number
  image_height: number
  objects: DetectedObject[]
}

/**
 * Parses a data channel payload, returning null when it is unusable.
 *
 * A malformed or future-versioned frame must never break the stream, so this
 * rejects rather than throws.
 */
export function parseDetectionFrame(raw: string): DetectionFrame | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }

  if (typeof parsed !== 'object' || parsed === null) return null
  const frame = parsed as Partial<DetectionFrame>

  if (frame.version !== SUPPORTED_SCHEMA_VERSION) return null
  if (typeof frame.image_width !== 'number' || typeof frame.image_height !== 'number') return null
  if (!Array.isArray(frame.objects)) return null
  if (frame.image_width <= 0 || frame.image_height <= 0) return null

  return frame as DetectionFrame
}
