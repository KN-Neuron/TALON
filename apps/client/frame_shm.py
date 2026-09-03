"""Reads camera frames the perception module publishes in shared memory.

The C++ perception module (`./run.sh` at the repo root) owns the camera. This
client does not open a capture device of its own -- it attaches to the module's
shared memory segment and reads frames the module has already grabbed and,
optionally, drawn on.

Two streams are published; pick one by name:
  "raw"        the untouched camera image
  "annotated"  the same image with detection boxes and labels drawn on

## Why shared memory

A 640x480 BGR frame is ~920 KB; at 30 fps that is 27 MB/s. Pushing that through
a socket would copy every byte through the kernel twice. Here the reader maps
the same pages the writer wrote, so the cost is close to zero. The trade-off is
that both processes must run on the same machine.

## How the synchronisation works

The segment holds a ring of slots. Each slot carries a `sequence` counter:
odd means a write is in progress, even means the frame is complete.

To read a slot: note the sequence, copy the pixels, then check the sequence
again. If it changed, or was odd to begin with, the writer overwrote the slot
mid-copy and the data is suspect, so the read is retried on the next attempt.

Nothing locks. The writer never waits for a reader, and a slow reader drops
frames instead of stalling detection -- which is what you want for a live view.
"""

import struct
from dataclasses import dataclass
from multiprocessing import resource_tracker, shared_memory
from typing import Self

import numpy as np
from loguru import logger

# Must match frameshm::kLayoutVersion in include/FrameServer.hpp. A mismatch
# means the two sides disagree about the byte layout, so we refuse to attach
# rather than misread the memory.
LAYOUT_VERSION = 1
MAGIC = 0x544C4E46  # "TLNF"

# struct SegmentHeader: 8 x uint32
_SEGMENT_HEADER = struct.Struct("<8I")
# struct SlotHeader: 4 x uint32, uint64, int64, 2 x uint32
_SLOT_HEADER = struct.Struct("<4IQqII")

# Slot headers start on a page boundary, and so does the first slot.
_PAGE = 4096


def _align_up(value: int, alignment: int = _PAGE) -> int:
    return (value + alignment - 1) // alignment * alignment


class FrameUnavailable(RuntimeError):
    """The perception module is not publishing frames."""


@dataclass(frozen=True)
class SharedFrame:
    """One frame copied out of the segment."""

    image: np.ndarray  # BGR, shape (height, width, channels)
    frame_id: int
    timestamp_ms: int


class FrameReader:
    """Attaches to a perception module's frame segment.

    The module must already be running: the segment is created by the writer,
    never by the reader.
    """

    def __init__(self, stream_name: str = "raw", read_retries: int = 3):
        self.segment_name = f"talon.{stream_name}"
        self.read_retries = read_retries

        self._shm: shared_memory.SharedMemory | None = None
        self._buffer: memoryview | None = None

        self._slot_count = 0
        self._slot_stride = 0
        self._slots_offset = 0

        self._last_frame_id = -1

    def _attach(self) -> None:
        try:
            self._shm = shared_memory.SharedMemory(name=self.segment_name)
        except FileNotFoundError as error:
            raise FrameUnavailable(
                f"Brak segmentu '{self.segment_name}'. "
                "Uruchom modul percepcji (./run.sh) przed klientem."
            ) from error

        # Python's resource_tracker assumes any segment a process touches is
        # its own and unlinks it at exit. Here the C++ module owns the segment
        # -- unlinking it from the reader would pull it out from under the
        # writer. Unregister so only the writer's own cleanup destroys it.
        try:
            resource_tracker.unregister(self._shm._name, "shared_memory")
        except Exception:  # pragma: no cover - private API, best effort
            logger.debug("Nie udalo sie wyrejestrowac segmentu z resource_tracker")

        self._buffer = memoryview(self._shm.buf)

        (
            magic,
            layout_version,
            slot_count,
            slot_stride,
            _max_width,
            _max_height,
            _max_channels,
            _latest,
        ) = _SEGMENT_HEADER.unpack_from(self._buffer, 0)

        # The writer stamps magic last, so its absence means the segment is
        # still being set up.
        if magic != MAGIC:
            self.close()
            raise FrameUnavailable(
                f"Segment '{self.segment_name}' nie jest gotowy (zly magic)."
            )

        if layout_version != LAYOUT_VERSION:
            self.close()
            raise FrameUnavailable(
                f"Niezgodna wersja ukladu pamieci: modul ma {layout_version}, "
                f"klient obsluguje {LAYOUT_VERSION}. Przebuduj oba."
            )

        self._slot_count = slot_count
        self._slot_stride = slot_stride
        self._slots_offset = _align_up(_SEGMENT_HEADER.size)

        logger.info(
            f"Czytam klatki z '{self.segment_name}' "
            f"({slot_count} slotow po {slot_stride} B)"
        )

    def _read_slot(self, index: int) -> SharedFrame | None:
        """Copies one slot, returning None if the writer raced us."""
        assert self._buffer is not None

        base = self._slots_offset + index * self._slot_stride
        (
            sequence_before,
            width,
            height,
            channels,
            frame_id,
            timestamp_ms,
            data_bytes,
            _reserved,
        ) = _SLOT_HEADER.unpack_from(self._buffer, base)

        # Odd sequence means a write is in flight.
        if sequence_before % 2 != 0:
            return None
        if width == 0 or height == 0 or data_bytes == 0:
            return None

        pixels_at = base + _SLOT_HEADER.size
        raw = bytes(self._buffer[pixels_at : pixels_at + data_bytes])

        # If the counter moved, the writer overwrote this slot while we copied,
        # so the bytes may be a mix of two frames.
        (sequence_after,) = struct.unpack_from("<I", self._buffer, base)
        if sequence_after != sequence_before:
            return None

        image = np.frombuffer(raw, dtype=np.uint8).reshape(
            (height, width, channels)
        )
        return SharedFrame(
            image=image, frame_id=frame_id, timestamp_ms=timestamp_ms
        )

    def read(self) -> SharedFrame | None:
        """Returns the newest complete frame, or None if none could be read.

        None is normal: it means the writer was mid-update every time we
        looked. Callers should try again rather than treat it as an error.
        """
        if self._buffer is None:
            raise RuntimeError("FrameReader must be used as a context manager")

        for _ in range(self.read_retries):
            (latest_slot,) = struct.unpack_from(
                "<I", self._buffer, _SEGMENT_HEADER.size - 4
            )
            if latest_slot >= self._slot_count:
                continue

            frame = self._read_slot(latest_slot)
            if frame is not None:
                self._last_frame_id = frame.frame_id
                return frame

        return None

    def close(self) -> None:
        self._buffer = None
        if self._shm is not None:
            self._shm.close()
            self._shm = None

    def __enter__(self) -> Self:
        self._attach()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
