"""A single peer connection wrapper."""

from __future__ import annotations

import asyncio
import time

from kwartel.net.framing import ProtocolError, write_message


class Peer:
    """Wraps one reader/writer pair for a connected peer.

    ``node_id`` is learned from the handshake (32 raw bytes).  ``addr`` is the
    remote socket address.  ``last_seen`` tracks the last successful read or
    write.  ``alive`` is false once the peer is known to be gone.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        node_id: bytes,
        addr,
        listen_port: int | None = None,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.node_id = node_id
        self.addr = addr
        self.listen_port = listen_port
        self.last_seen = time.monotonic()
        self.alive = True

    @property
    def host(self) -> str:
        """The remote host (from the socket address)."""
        if isinstance(self.addr, (tuple, list)) and self.addr:
            return str(self.addr[0])
        return str(self.addr)

    async def send(self, topic: str, payload: bytes) -> None:
        """Write one message to this peer.

        Any write failure marks the peer dead and closes it, so callers do not
        have to catch the exception.  The write is bounded so a half-dead peer
        cannot stall gossip for the full idle timeout.
        """
        if not self.alive:
            return
        try:
            await write_message(self.writer, topic, payload, timeout=5.0)
            self.last_seen = time.monotonic()
        except (ProtocolError, ConnectionError, TimeoutError, OSError):
            await self.close()

    async def close(self) -> None:
        """Close the underlying transport, idempotently.

        Fire-and-forget: we close the transport but do not await ``wait_closed``,
        which can stall indefinitely on Windows Proactor when a reader is still
        active. The remote sees the FIN and its read loop unblocks.
        """
        self.alive = False
        try:
            self.writer.close()
        except (ConnectionError, OSError, RuntimeError):
            pass
