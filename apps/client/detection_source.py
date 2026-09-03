"""Reads detection frames from the perception process over a Unix socket.

`SOCK_DGRAM` gives message boundaries for free: one `sendto` from the producer
is one `recv` here, so no length framing is needed. When the reader falls
behind, the kernel drops datagrams rather than queueing them, which is what we
want -- a stale detection is worthless.
"""

import asyncio
import os
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from loguru import logger

# Large enough for a frame with many tracked objects; datagrams above this are
# truncated by the kernel, so keep it generous.
MAX_DATAGRAM_BYTES = 65536


class DetectionSource:
    """Receives detection datagrams on a Unix domain socket.

    The client owns the socket file: it is unlinked and recreated on start so a
    leftover file from a crashed run does not block binding.
    """

    def __init__(self, socket_path: str, receive_buffer_bytes: int = 1 << 20):
        self.socket_path = Path(socket_path)
        self.receive_buffer_bytes = receive_buffer_bytes
        self._socket: socket.socket | None = None

    def _bind(self) -> socket.socket:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        # A stale socket file from an unclean shutdown would make bind() fail.
        if self.socket_path.exists():
            self.socket_path.unlink()

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.setblocking(False)
        # A bigger receive buffer absorbs short scheduling stalls; beyond it the
        # kernel drops datagrams, which is the desired backpressure.
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.receive_buffer_bytes)
        except OSError:
            logger.warning("Could not enlarge the detection socket receive buffer")
        sock.bind(str(self.socket_path))
        return sock

    async def frames(self) -> AsyncIterator[bytes]:
        """Yields raw datagrams as they arrive.

        Payloads are yielded unparsed: the client forwards bytes verbatim, so
        parsing here would only cost latency.
        """
        if self._socket is None:
            raise RuntimeError("DetectionSource must be used as a context manager")

        loop = asyncio.get_running_loop()
        while True:
            try:
                payload = await loop.sock_recv(self._socket, MAX_DATAGRAM_BYTES)
            except (BlockingIOError, InterruptedError):
                continue
            except OSError as error:
                logger.warning(f"Detection socket closed: {error}")
                return

            if payload:
                yield payload

    def __enter__(self) -> "DetectionSource":
        self._socket = self._bind()
        logger.info(f"Listening for detections on {self.socket_path}")
        return self

    def __exit__(self, *exc_info) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass


@asynccontextmanager
async def detection_source(socket_path: str) -> AsyncIterator[DetectionSource]:
    with DetectionSource(socket_path) as source:
        yield source
