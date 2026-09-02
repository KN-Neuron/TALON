"""Detection frames received from the perception process.

The perception process (C++, on the edge AI device) writes one JSON message per
processed frame to a Unix domain socket. This module models that schema so the
client can validate frames before forwarding them.

See `docs/detection-protocol.md` for the wire format.
"""

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


class BoundingBox(BaseModel):
    """Axis-aligned box in pixels, origin at the top-left of the frame."""

    left: int
    top: int
    width: int
    height: int


class Position(BaseModel):
    """Object position in the drone's frame, in metres."""

    lateral_m: float = Field(description="Sideways offset; negative is left")
    forward_m: float = Field(description="Distance ahead of the drone")


class DetectedObject(BaseModel):
    track_id: int = Field(description="Stable across frames for the same object")
    class_id: int = Field(description="Numeric class id from the detector")
    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    box: BoundingBox

    position: Position | None = None
    closing_speed_mps: float | None = Field(
        default=None, description="Rate of change of forward_m; negative approaches"
    )
    time_to_collision_s: float | None = Field(
        default=None, description="Seconds to impact at the current closing speed"
    )

    frames_since_seen: int = Field(
        default=0, description="0 when detected this frame; grows while coasting"
    )


class DetectionFrame(BaseModel):
    version: int = SCHEMA_VERSION
    frame_id: int
    timestamp_ms: int
    frame_interval_s: float
    image_width: int
    image_height: int
    objects: list[DetectedObject] = Field(default_factory=list)
