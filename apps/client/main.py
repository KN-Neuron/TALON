import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiortc import RTCPeerConnection
from loguru import logger

from camera import Camera
from detection_publisher import DetectionPublisher, create_detections_channel
from detection_source import DetectionSource
from settings import Settings, get_settings
from whip_client import WhipClient


@asynccontextmanager
async def peer_connection() -> AsyncIterator[RTCPeerConnection]:
    pc = RTCPeerConnection()
    try:
        yield pc
    finally:
        await pc.close()


async def _wait_for_disconnect(pc: RTCPeerConnection) -> str:
    """Resolves when the peer connection leaves a usable state."""
    disconnected = asyncio.Event()
    final_state = "closed"

    @pc.on("connectionstatechange")
    def on_state_change() -> None:
        nonlocal final_state
        if pc.connectionState in {"failed", "closed", "disconnected"}:
            final_state = pc.connectionState
            disconnected.set()

    await disconnected.wait()
    return final_state


async def _run_session(settings: Settings, camera: Camera) -> None:
    """Publishes video (and detections) until the connection drops."""
    async with peer_connection() as pc:
        # A fresh track per session: tracks cannot outlive their peer connection.
        pc.addTrack(camera.track())

        detection_task: asyncio.Task | None = None
        detection_source: DetectionSource | None = None

        if settings.enable_detections:
            # Created before the offer so the SDP carries an m=application
            # section; without it the channel never negotiates.
            channel = create_detections_channel(pc)
            detection_source = DetectionSource(settings.detection_socket_path)

        whip_client = WhipClient(settings.backend_url, settings.stream_id)
        async with whip_client.published(pc):
            logger.info(
                f"Streaming camera to backend as stream '{settings.stream_id}'"
            )

            if settings.enable_detections and detection_source is not None:
                publisher = DetectionPublisher(channel)
                with detection_source as source:
                    detection_task = asyncio.create_task(publisher.run(source.frames()))
                    try:
                        state = await _wait_for_disconnect(pc)
                    finally:
                        detection_task.cancel()
                        await asyncio.gather(detection_task, return_exceptions=True)
            else:
                state = await _wait_for_disconnect(pc)

            logger.warning(f"Connection entered state '{state}'")


async def main() -> None:
    settings = get_settings()
    delay = settings.reconnect_initial_delay_s

    with Camera(settings.camera_index) as camera:
        while True:
            try:
                await _run_session(settings, camera)
                # A clean return still means the session ended; reconnect.
                delay = settings.reconnect_initial_delay_s
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error(f"Session failed: {error}")

            logger.info(f"Reconnecting in {delay:.1f}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, settings.reconnect_max_delay_s)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
