from typing import Self

import cv2
from aiortc import VideoStreamTrack
from av import VideoFrame


class CameraStreamTrack(VideoStreamTrack):
    def __init__(self, camera_index: int):
        super().__init__()
        self.capture = cv2.VideoCapture(camera_index)
        if not self.capture.isOpened():
            raise RuntimeError(
                f"Nie udało się otworzyć kamery o indeksie {camera_index}"
            )

    async def recv(self) -> VideoFrame:
        pts, time_base = await self.next_timestamp()
        ok, frame = self.capture.read()
        if not ok:
            raise RuntimeError("Nie udało się odczytać klatki z kamery")

        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    def stop(self):
        super().stop()
        self.capture.release()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()
