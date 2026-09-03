"""Stand-in for the C++ perception process.

Emits synthetic detection frames on the Unix socket the client listens on, so
the relay, the data channel and the browser overlay can be exercised before the
edge AI device is wired in.

    uv run mock_perception.py
"""

import asyncio
import json
import math
import socket
import time

from loguru import logger

from detections import (
    SCHEMA_VERSION,
    BoundingBox,
    DetectedObject,
    DetectionFrame,
    Position,
)
from settings import get_settings

FRAMES_PER_SECOND = 30
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480

# (track_id, class_id, class_name, approach speed in m/s)
SIMULATED_OBJECTS = [
    (1, 39, "bottle", -0.8),
    (2, 0, "person", -0.35),
    (3, 56, "chair", 0.0),
]


def _simulate_object(
    track_id: int,
    class_id: int,
    class_name: str,
    closing_speed_mps: float,
    elapsed_s: float,
) -> DetectedObject:
    """Builds one object that drifts across frame and towards the drone."""
    phase = elapsed_s * 0.6 + track_id * 2.0

    # Distance oscillates so time_to_collision moves through interesting values.
    forward_m = 3.0 + 2.0 * math.sin(phase * 0.5) + track_id * 0.5
    lateral_m = 1.4 * math.sin(phase)

    # Nearer objects appear larger and lower in frame.
    height = int(max(40.0, 220.0 / max(forward_m, 0.6)))
    width = int(height * 0.55)
    centre_x = IMAGE_WIDTH / 2 + lateral_m * (IMAGE_WIDTH / 6)
    centre_y = IMAGE_HEIGHT / 2 + (height * 0.15)

    left = int(max(0, min(IMAGE_WIDTH - width, centre_x - width / 2)))
    top = int(max(0, min(IMAGE_HEIGHT - height, centre_y - height / 2)))

    time_to_collision_s = None
    if closing_speed_mps < 0:
        time_to_collision_s = round(forward_m / abs(closing_speed_mps), 2)

    return DetectedObject(
        track_id=track_id,
        class_id=class_id,
        class_name=class_name,
        confidence=round(0.72 + 0.2 * abs(math.cos(phase)), 2),
        box=BoundingBox(left=left, top=top, width=width, height=height),
        position=Position(
            lateral_m=round(lateral_m, 2), forward_m=round(forward_m, 2)
        ),
        closing_speed_mps=closing_speed_mps,
        time_to_collision_s=time_to_collision_s,
        # Occasionally coast a track to exercise the overlay's fade-out.
        frames_since_seen=int(max(0, math.sin(phase * 0.35) * 6 - 3)),
    )


async def main() -> None:
    settings = get_settings()
    frame_interval_s = 1.0 / FRAMES_PER_SECOND

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    logger.info(
        f"Emitting mock detections to {settings.detection_socket_path} "
        f"at {FRAMES_PER_SECOND} fps (schema v{SCHEMA_VERSION})"
    )

    frame_id = 0
    started = time.monotonic()
    warned_missing_listener = False

    try:
        while True:
            frame_started = time.monotonic()
            elapsed_s = frame_started - started

            frame = DetectionFrame(
                frame_id=frame_id,
                timestamp_ms=int(time.time() * 1000),
                frame_interval_s=round(frame_interval_s, 4),
                image_width=IMAGE_WIDTH,
                image_height=IMAGE_HEIGHT,
                objects=[
                    _simulate_object(*spec, elapsed_s) for spec in SIMULATED_OBJECTS
                ],
            )

            payload = json.dumps(frame.model_dump(exclude_none=True)).encode("utf-8")
            try:
                sock.sendto(payload, str(settings.detection_socket_path))
                warned_missing_listener = False
            except (FileNotFoundError, ConnectionRefusedError):
                # The client is not running yet; keep trying quietly.
                if not warned_missing_listener:
                    logger.warning("No listener on the detection socket yet; waiting")
                    warned_missing_listener = True
            except OSError as error:
                logger.warning(f"Could not send frame {frame_id}: {error}")

            frame_id += 1
            elapsed_this_frame = time.monotonic() - frame_started
            await asyncio.sleep(max(0.0, frame_interval_s - elapsed_this_frame))
    finally:
        sock.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
