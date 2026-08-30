import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import requests
from aiortc import RTCPeerConnection, RTCSessionDescription
from loguru import logger

from webrtc import wait_for_ice_gathering_complete


class WhipClient:
    def __init__(self, backend_url: str, stream_id: str):
        self.backend_url = backend_url
        self.stream_id = stream_id
        self.resource_url: str | None = None

    async def publish(self, pc: RTCPeerConnection) -> str | None:
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        await wait_for_ice_gathering_complete(pc)

        whip_url = f"{self.backend_url}/whip/{self.stream_id}"
        logger.info(f"Connecting to {whip_url} ...")
        response = await asyncio.to_thread(
            requests.post,
            whip_url,
            data=pc.localDescription.sdp.encode("utf-8"),
            headers={"Content-Type": "application/sdp"},
        )
        response.raise_for_status()

        resource_url = response.headers.get("Location")
        if resource_url and not resource_url.startswith("http"):
            resource_url = self.backend_url + resource_url

        await pc.setRemoteDescription(
            RTCSessionDescription(sdp=response.text, type="answer")
        )

        self.resource_url = resource_url
        return resource_url

    async def unpublish(self) -> None:
        if not self.resource_url:
            return
        try:
            await asyncio.to_thread(requests.delete, self.resource_url)
        except requests.RequestException:
            pass
        self.resource_url = None

    @asynccontextmanager
    async def published(self, pc: RTCPeerConnection) -> AsyncIterator[str | None]:
        resource_url = await self.publish(pc)
        try:
            yield resource_url
        finally:
            logger.info("Disconnecting...")
            await self.unpublish()
