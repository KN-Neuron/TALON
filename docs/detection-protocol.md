# Detection protocol

The perception process (C++ on the edge AI device) emits one JSON message per
processed frame. The Python client forwards those bytes verbatim over a WebRTC
data channel named `detections`; the Go relay fans them out to every subscriber
without parsing them. The browser renders them as an overlay on top of the video.

Nothing between the producer and the browser inspects the payload, so the schema
can change without touching Go.

## Transport

| Hop | Mechanism |
| --- | --- |
| C++ perception -> Python client | Unix domain socket, `SOCK_DGRAM`, default `/tmp/talon-detections.sock` |
| Python client -> Go relay | WebRTC data channel `detections`, unordered, no retransmits |
| Go relay -> browser | WebRTC data channel `detections`, unordered, no retransmits |

`SOCK_DGRAM` gives message boundaries for free: one `sendto` is one frame, so no
length framing is needed. If the reader falls behind, the kernel drops
datagrams, which is the desired behaviour -- a stale detection is worthless.

The data channel is unordered with no retransmits for the same reason.
Retransmitting a frame that has already been superseded only adds latency.

## Message

```json
{
  "version": 1,
  "frame_id": 4821,
  "timestamp_ms": 1732104000123,
  "frame_interval_s": 0.033,
  "image_width": 640,
  "image_height": 480,
  "objects": [
    {
      "track_id": 3,
      "class_id": 39,
      "class_name": "bottle",
      "confidence": 0.88,
      "box": { "left": 100, "top": 120, "width": 40, "height": 110 },
      "position": { "lateral_m": -0.45, "forward_m": 2.34 },
      "closing_speed_mps": -0.8,
      "time_to_collision_s": 2.9,
      "frames_since_seen": 0
    }
  ]
}
```

### Top level

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | int | Schema version. Bump on any breaking change. Consumers ignore messages whose version they do not understand. |
| `frame_id` | int | Monotonic counter from the perception process. Used to drop out-of-order messages. |
| `timestamp_ms` | int | Producer wall clock, milliseconds since the Unix epoch. See "Clocks" below. |
| `frame_interval_s` | float | Seconds since the previous processed frame. Inverse is the perception FPS. |
| `image_width` | int | Width in pixels of the frame the boxes were computed on. |
| `image_height` | int | Height in pixels of that frame. |
| `objects` | array | Tracked objects. May be empty; the message is still sent so consumers can tell "nothing detected" from "producer stopped". |

### Object

| Field | Type | Meaning |
| --- | --- | --- |
| `track_id` | int | Stable across frames for the same physical object. Drives overlay continuity. |
| `class_id` | int | Numeric class from the detector (COCO id for a stock YOLO). |
| `class_name` | string | Human-readable class label. |
| `confidence` | float | Detector confidence, `0.0`-`1.0`. |
| `box` | object | Axis-aligned bounding box in pixels, origin top-left. |
| `box.left` | int | Distance from the left edge of the frame. |
| `box.top` | int | Distance from the top edge of the frame. |
| `box.width` | int | Box width. |
| `box.height` | int | Box height. |
| `position` | object | Estimated object position in the drone's frame, metres. Optional; omit when unavailable. |
| `position.lateral_m` | float | Sideways offset. Negative is left of centre, positive is right. |
| `position.forward_m` | float | Distance ahead of the drone. |
| `closing_speed_mps` | float | Rate of change of `forward_m`. **Negative means approaching.** Optional. |
| `time_to_collision_s` | float | Seconds until impact at the current closing speed. Optional; omitted when the object is not approaching. |
| `frames_since_seen` | int | `0` when detected in this frame, incrementing while the tracker coasts on prediction alone. |

### Coordinates

Boxes are in **pixels** relative to `image_width` x `image_height`, not
normalised. Consumers scale to their own display size:

```
scale_x = displayed_width  / image_width
scale_y = displayed_height / image_height
```

Pixels were chosen over normalised `0.0`-`1.0` coordinates because the producer
already works in pixels and the conversion would be lossy in both directions.
The cost is that every consumer must scale; `image_width` and `image_height`
are always present so this is mechanical.

Note that the displayed video may be letterboxed if its aspect ratio differs
from the overlay surface. Consumers must account for the offset, not just the
scale.

### Optional fields

`position`, `closing_speed_mps` and `time_to_collision_s` are optional: a
detector without depth estimation emits boxes only. Consumers must render
correctly when they are absent. `track_id`, `class_id`, `class_name`,
`confidence`, `box` and `frames_since_seen` are always present.

### Stale tracks

`frames_since_seen` counts frames where the tracker predicted the object
without a matching detection. The reference overlay fades an object out as this
grows and stops drawing it past a threshold. The producer decides when to drop
a track entirely; consumers should not assume a track ends with a final
message.

## Clocks

`timestamp_ms` comes from the producer's system clock. It is **not**
synchronised with the video's presentation timeline, so an overlay driven by it
will lead the picture by the end-to-end video latency -- typically tens to
hundreds of milliseconds.

This is acceptable for monitoring and demos. Frame-accurate alignment would
require carrying a shared timebase through the WebRTC media pipeline, which is
out of scope here.

Consumers should treat `timestamp_ms` as useful for measuring end-to-end
latency and for detecting a stalled producer, not for synchronising to video.

## Raw frames

Consumers that want pixels rather than metadata subscribe to the same stream
over WHEP and ignore the data channel. See `docs/consuming-streams.md`.
