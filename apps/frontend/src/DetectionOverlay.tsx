import { useEffect, useRef } from 'react'
import type { DetectedObject, DetectionFrame } from './detections'

/** Objects coasting longer than this are not drawn at all. */
const MAX_FRAMES_SINCE_SEEN = 8
/** Below this time-to-collision an object is drawn as a warning. */
const COLLISION_WARNING_S = 2.0

const COLOUR_NORMAL = '#38bdf8'
const COLOUR_WARNING = '#f87171'
const FONT = '13px ui-monospace, SFMono-Regular, Menlo, monospace'

interface Props {
  /** Latest frame, or null when none has arrived yet. */
  frame: DetectionFrame | null
  /** The video element the overlay is drawn on top of. */
  videoRef: React.RefObject<HTMLVideoElement | null>
}

/**
 * Maps source-frame pixels onto the displayed video.
 *
 * The video is letterboxed when its aspect ratio differs from the element, so
 * scaling alone is not enough -- the offset of the painted area matters too.
 */
function computeVideoFit(
  video: HTMLVideoElement,
  imageWidth: number,
  imageHeight: number,
) {
  const elementWidth = video.clientWidth
  const elementHeight = video.clientHeight

  // Fall back to the frame's own dimensions before metadata has loaded.
  const sourceWidth = video.videoWidth || imageWidth
  const sourceHeight = video.videoHeight || imageHeight

  const scale = Math.min(elementWidth / sourceWidth, elementHeight / sourceHeight)
  const paintedWidth = sourceWidth * scale
  const paintedHeight = sourceHeight * scale

  return {
    // Detection boxes are in image_* pixels, which may differ from the encoded
    // video size, so bridge both.
    scaleX: (paintedWidth / imageWidth),
    scaleY: (paintedHeight / imageHeight),
    offsetX: (elementWidth - paintedWidth) / 2,
    offsetY: (elementHeight - paintedHeight) / 2,
  }
}

function isApproaching(object: DetectedObject): boolean {
  return (
    object.time_to_collision_s !== undefined &&
    object.time_to_collision_s <= COLLISION_WARNING_S
  )
}

/** Builds the label, omitting fields the producer did not send. */
function buildLabel(object: DetectedObject): string {
  const parts = [`${object.class_name} ${(object.confidence * 100).toFixed(0)}%`]

  if (object.position) {
    parts.push(`${object.position.forward_m.toFixed(1)}m`)
  }
  if (object.time_to_collision_s !== undefined) {
    parts.push(`TTC ${object.time_to_collision_s.toFixed(1)}s`)
  }
  return parts.join('  ')
}

function drawObject(
  context: CanvasRenderingContext2D,
  object: DetectedObject,
  fit: ReturnType<typeof computeVideoFit>,
) {
  // Fade out as the tracker coasts without fresh detections.
  const freshness = 1 - object.frames_since_seen / MAX_FRAMES_SINCE_SEEN
  context.globalAlpha = Math.max(0.15, freshness)

  const colour = isApproaching(object) ? COLOUR_WARNING : COLOUR_NORMAL
  const left = object.box.left * fit.scaleX + fit.offsetX
  const top = object.box.top * fit.scaleY + fit.offsetY
  const width = object.box.width * fit.scaleX
  const height = object.box.height * fit.scaleY

  context.strokeStyle = colour
  context.lineWidth = isApproaching(object) ? 3 : 2
  context.strokeRect(left, top, width, height)

  const label = buildLabel(object)
  context.font = FONT
  const textWidth = context.measureText(label).width
  const labelHeight = 18

  // Keep the label inside the frame when the box sits at the top edge.
  const labelTop = top - labelHeight < 0 ? top + height : top - labelHeight

  context.fillStyle = colour
  context.fillRect(left, labelTop, textWidth + 10, labelHeight)
  context.fillStyle = '#0b1220'
  context.fillText(label, left + 5, labelTop + 13)

  context.globalAlpha = 1
}

/**
 * Draws detection boxes over the video.
 *
 * Rendering is driven by requestAnimationFrame rather than by message arrival:
 * at 30 fps the two would otherwise contend, and only the newest frame matters.
 */
function DetectionOverlay({ frame, videoRef }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  // Held in a ref so the animation loop reads the newest frame without the
  // effect restarting on every message.
  const frameRef = useRef<DetectionFrame | null>(null)

  useEffect(() => {
    frameRef.current = frame
  }, [frame])

  useEffect(() => {
    const canvas = canvasRef.current
    const video = videoRef.current
    if (!canvas || !video) return

    const context = canvas.getContext('2d')
    if (!context) return

    let animationHandle = 0

    const render = () => {
      animationHandle = requestAnimationFrame(render)

      const displayWidth = video.clientWidth
      const displayHeight = video.clientHeight
      if (displayWidth === 0 || displayHeight === 0) return

      // Match the backing store to the element, accounting for HiDPI.
      const ratio = window.devicePixelRatio || 1
      if (canvas.width !== displayWidth * ratio || canvas.height !== displayHeight * ratio) {
        canvas.width = displayWidth * ratio
        canvas.height = displayHeight * ratio
        canvas.style.width = `${displayWidth}px`
        canvas.style.height = `${displayHeight}px`
      }

      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      context.clearRect(0, 0, displayWidth, displayHeight)

      const current = frameRef.current
      if (!current) return

      const fit = computeVideoFit(video, current.image_width, current.image_height)
      for (const object of current.objects) {
        if (object.frames_since_seen >= MAX_FRAMES_SINCE_SEEN) continue
        drawObject(context, object, fit)
      }
    }

    animationHandle = requestAnimationFrame(render)
    return () => cancelAnimationFrame(animationHandle)
  }, [videoRef])

  return <canvas ref={canvasRef} className="detection-overlay" />
}

export default DetectionOverlay
