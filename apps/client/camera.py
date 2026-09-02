from typing import Self

import cv2
from aiortc import VideoStreamTrack
from av import VideoFrame


class Camera:
    """Owns the capture device.

    The device is opened once and kept open across reconnects; each WebRTC
    session gets a fresh track reading from it, because a track that has been
    attached to a closed peer connection cannot be reused.
    """

    def __init__(self, camera_index: int):
        self.capture = cv2.VideoCapture(camera_index)
        if not self.capture.isOpened():
            raise RuntimeError(
                f"Nie udało się otworzyć kamery o indeksie {camera_index}"
            )

    def track(self) -> "CameraStreamTrack":
        return CameraStreamTrack(self.capture)

    def release(self) -> None:
        self.capture.release()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> None:
        self.release()


class CameraStreamTrack(VideoStreamTrack):
    """A single session's view of the camera.

    Does not own the capture device: stopping the track ends the session but
    leaves the camera open for the next one.
    """

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
