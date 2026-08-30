import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiortc import RTCPeerConnection
from loguru import logger

from camera import CameraStreamTrack
from settings import get_settings
from whip_client import WhipClient


@asynccontextmanager
async def peer_connection() -> AsyncIterator[RTCPeerConnection]:
    pc = RTCPeerConnection()
    try:
        yield pc
    finally:
        await pc.close()


async def main():
    settings = get_settings()

    with CameraStreamTrack(settings.camera_index) as track:
        async with peer_connection() as pc:
            pc.addTrack(track)

            whip_client = WhipClient(settings.backend_url, settings.stream_id)
            async with whip_client.published(pc):
                logger.info(
                    "Connected. Streaming camera feed to backend. Press Ctrl+C to stop."
                )
                while True:
                    await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
