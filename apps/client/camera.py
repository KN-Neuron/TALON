"""Video sources for the WebRTC client.

Two sources exist:

`PerceptionModuleCamera` reads frames the C++ perception module publishes in
shared memory. This is the normal path: the module owns the camera, runs
detection on every frame, and hands the pixels over -- so only one process
opens the capture device.

`LocalCamera` opens a capture device directly. It is the fallback for running
the client on its own, without the perception module.
"""

import asyncio
from typing import Protocol, Self

import cv2
from aiortc import VideoStreamTrack
from av import VideoFrame
from loguru import logger

from frame_shm import FrameReader, FrameUnavailable

# How long to wait for a frame before giving up on the source.
FRAME_TIMEOUT_S = 5.0
# How long to sleep when the reader loses a race with the writer. Short enough
# to be invisible at 30 fps.
FRAME_RETRY_S = 0.002


class VideoSource(Protocol):
    """Anything that can hand out fresh tracks for successive sessions.

    The source outlives individual WebRTC sessions -- a track cannot be
    reattached after its peer connection closes, so each session takes a new
    one while the underlying camera or segment stays open.
    """

    def track(self) -> VideoStreamTrack: ...
    def close(self) -> None: ...
    def __enter__(self) -> "VideoSource": ...
    def __exit__(self, *exc_info) -> None: ...


class PerceptionModuleCamera:
    """Frames from the C++ perception module's shared memory.

    The module must be running first: it creates the segment, this only
    attaches. Which stream to read is chosen by name -- "raw" for the untouched
    camera image, "annotated" for the one with detection boxes drawn on.
    """

    def __init__(self, stream_name: str = "raw"):
        self.stream_name = stream_name
        self._reader = FrameReader(stream_name)
        self._reader.__enter__()

    def track(self) -> "SharedMemoryTrack":
        return SharedMemoryTrack(self._reader)

    def close(self) -> None:
        self._reader.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


class SharedMemoryTrack(VideoStreamTrack):
    """A single session's view of the shared frame stream.

    Does not own the reader: ending a session leaves the segment attached for
    the next one.
    """

    def __init__(self, reader: FrameReader):
        super().__init__()
        self._reader = reader
        self._last_frame_id = -1

    async def recv(self) -> VideoFrame:
        pts, time_base = await self.next_timestamp()

        loop = asyncio.get_running_loop()
        deadline = loop.time() + FRAME_TIMEOUT_S

        while True:
            frame = self._reader.read()

            # A fresh frame, or at least one we have not sent yet.
            if frame is not None and frame.frame_id != self._last_frame_id:
                self._last_frame_id = frame.frame_id
                video_frame = VideoFrame.from_ndarray(frame.image, format="bgr24")
                video_frame.pts = pts
                video_frame.time_base = time_base
                return video_frame

            if loop.time() > deadline:
                raise RuntimeError(
                    "Modul percepcji nie dostarcza klatek "
                    f"(brak nowej klatki przez {FRAME_TIMEOUT_S:.0f}s). "
                    "Czy nadal dziala?"
                )

            # None means we lost a race with the writer, or the module has not
            # produced a new frame yet. Either way: look again shortly.
            await asyncio.sleep(FRAME_RETRY_S)


class LocalCamera:
    """Opens a capture device directly.

    Fallback for running the client without the perception module. Do not use
    both at once -- most systems allow only one process to open a camera.
    """

    def __init__(self, camera_index: int):
        self.capture = cv2.VideoCapture(camera_index)
        if not self.capture.isOpened():
            raise RuntimeError(
                f"Nie udało się otworzyć kamery o indeksie {camera_index}"
            )
        logger.warning(
            "Klient otworzyl kamere bezposrednio. "
            "Modul percepcji nie moze wtedy uzywac tego samego urzadzenia."
        )

    def track(self) -> "LocalCameraTrack":
        return LocalCameraTrack(self.capture)

    def close(self) -> None:
        self.capture.release()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


class LocalCameraTrack(VideoStreamTrack):
    """A single session's view of a local capture device."""

    def __init__(self, capture: cv2.VideoCapture):
        super().__init__()
        self.capture = capture

    async def recv(self) -> VideoFrame:
        pts, time_base = await self.next_timestamp()
        ok, frame = self.capture.read()
        if not ok:
            raise RuntimeError("Nie udało się odczytać klatki z kamery")

        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame


def open_video_source(
    source: str, stream_name: str, camera_index: int
) -> VideoSource:
    """Opens the configured source.

    "auto" prefers the perception module and falls back to a local camera when
    the module is not running, so the client works either way without
    reconfiguration.
    """
    if source == "local":
        return LocalCamera(camera_index)

    if source == "perception":
        return PerceptionModuleCamera(stream_name)

    try:
        return PerceptionModuleCamera(stream_name)
    except FrameUnavailable as error:
        logger.warning(f"{error}")
        logger.info("Wracam do lokalnej kamery.")
        return LocalCamera(camera_index)
