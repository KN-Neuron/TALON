"""Forwards detection frames onto the WebRTC data channel."""

import asyncio

from aiortc import RTCDataChannel, RTCPeerConnection
from loguru import logger

DETECTIONS_CHANNEL_LABEL = "detections"

# Above this many bytes queued on the channel, frames are dropped rather than
# queued. A detection that waits behind a backlog describes the past.
MAX_BUFFERED_BYTES = 256 * 1024


def create_detections_channel(pc: RTCPeerConnection) -> RTCDataChannel:
    """Creates the detections channel.

    Unordered with no retransmits: a late detection has already been superseded
    by a newer frame, so retransmitting it only adds latency.

    Must be called before the offer is created so that the SDP carries an
    `m=application` section.
    """
    return pc.createDataChannel(
        DETECTIONS_CHANNEL_LABEL, ordered=False, maxRetransmits=0
    )


class DetectionPublisher:
    """Pumps datagrams from the perception socket onto the data channel."""

    def __init__(self, channel: RTCDataChannel):
        self.channel = channel
        self.forwarded = 0
        self.dropped = 0

    def _send(self, payload: bytes) -> None:
        if self.channel.readyState != "open":
            self.dropped += 1
            return

        # Drop rather than queue: the next frame is always more useful.
        if self.channel.bufferedAmount > MAX_BUFFERED_BYTES:
            self.dropped += 1
            return

        self.channel.send(payload)
        self.forwarded += 1

    async def run(self, frames) -> None:
        """Consumes an async iterator of raw datagrams until it ends."""
        report_interval_s = 10.0
        next_report = asyncio.get_running_loop().time() + report_interval_s

        async for payload in frames:
            self._send(payload)

            now = asyncio.get_running_loop().time()
            if now >= next_report:
                logger.info(
                    f"Detections forwarded={self.forwarded} dropped={self.dropped}"
                )
                next_report = now + report_interval_s
