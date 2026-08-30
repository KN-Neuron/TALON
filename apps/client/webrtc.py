import asyncio

from aiortc import RTCPeerConnection


async def wait_for_ice_gathering_complete(pc: RTCPeerConnection) -> None:
    if pc.iceGatheringState == "complete":
        return
    done = asyncio.Event()

    @pc.on("icegatheringstatechange")
    def on_change():
        if pc.iceGatheringState == "complete":
            done.set()

    await done.wait()
