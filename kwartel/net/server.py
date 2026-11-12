"""asyncio TCP server that accepts peers, handshakes, and relays messages."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from kwartel.net.config import NetConfig
from kwartel.net.framing import ProtocolError, read_message
from kwartel.net.handshake import (
    HandshakeError,
    handshake_as_connector,
    handshake_as_responder,
)
from kwartel.net.peer import Peer


@dataclass(frozen=True)
class ReceivedMessage:
    """A message received from a peer, tagged with that peer's node id."""

    node_id: bytes
    topic: str
    payload: bytes


class PeerBook:
    """Registry of live peers keyed by node id."""

    def __init__(self, max_peers: int) -> None:
        self.max_peers = max_peers
        self._peers: dict[bytes, Peer] = {}

    def add(self, peer: Peer) -> bool:
        """Add ``peer``; False if duplicate node_id or the book is full."""
        if peer.node_id in self._peers:
            return False
        if len(self._peers) >= self.max_peers:
            return False
        self._peers[peer.node_id] = peer
        return True

    def remove(self, peer: Peer) -> None:
        self._peers.pop(peer.node_id, None)

    def get(self, node_id: bytes) -> Peer | None:
        return self._peers.get(node_id)

    def all(self) -> list[Peer]:
        return list(self._peers.values())

    def clear(self) -> None:
        self._peers.clear()

    def __len__(self) -> int:
        return len(self._peers)


class Server:
    """An asyncio TCP server plus outbound peer connections.

    On accept it frame-reads a handshake, validates it, and registers the peer.
    Inbound messages are pushed to an internal queue readable via ``receive``.
    ``broadcast``/``send_to`` relay messages to live peers.
    """

    def __init__(self, config: NetConfig, node_id: bytes, genesis_hash: bytes) -> None:
        self.config = config
        self.node_id = node_id
        self.genesis_hash = genesis_hash
        self.book = PeerBook(config.max_peers)
        self._server: asyncio.Server | None = None
        self._received: asyncio.Queue[ReceivedMessage] = asyncio.Queue()
        self._read_tasks: set[asyncio.Task] = set()
        self._client_tasks: set[asyncio.Task] = set()
        self._port: int | None = None
        self.on_peer_connected = None

    @property
    def port(self) -> int:
        """The actual port the server is bound to (valid after ``start``)."""
        if self._port is None:
            raise RuntimeError("server has not started")
        return self._port

    async def start(self) -> None:
        """Begin listening on the configured host:port."""
        self._server = await asyncio.start_server(
            self._handle_client_wrapper, self.config.host, self.config.port
        )
        self._port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop listening and close all peers and read loops, idempotently."""
        for peer in self.book.all():
            await peer.close()
        self.book.clear()

        for task in list(self._read_tasks):
            task.cancel()
        pending = [t for t in self._read_tasks if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=2.0)
        self._read_tasks.clear()

        if self._server is not None:
            self._server.close()
            # Cancel inbound handler tasks so wait_closed() returns promptly.
            for task in list(self._client_tasks):
                task.cancel()
            pending = [t for t in self._client_tasks if not t.done()]
            if pending:
                await asyncio.wait(pending, timeout=2.0)
            self._client_tasks.clear()
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
            self._server = None

    async def connect_peer(self, host: str, port: int) -> Peer:
        """Open an outbound connection and perform the connector handshake."""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), self.config.handshake_timeout
        )
        try:
            remote = await handshake_as_connector(
                reader,
                writer,
                node_id=self.node_id,
                genesis_hash=self.genesis_hash,
                listen_port=self.port,
                timeout=self.config.handshake_timeout,
            )
        except (HandshakeError, ProtocolError, TimeoutError):
            writer.close()
            raise

        peer = Peer(reader, writer, remote.node_id, (host, port), remote.listen_port)
        if not self.book.add(peer):
            await peer.close()
            raise HandshakeError("duplicate peer node_id")
        self._spawn_reader(peer)
        await self._notify_connected(peer)
        return peer

    async def _notify_connected(self, peer: Peer) -> None:
        """Invoke the optional post-handshake callback, if set."""
        if self.on_peer_connected is not None:
            try:
                await self.on_peer_connected(peer)
            except Exception:
                # A callback failure must never break the connection handling.
                pass

    async def _handle_client_wrapper(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._client_tasks.add(task)
        try:
            await self._handle_client(reader, writer)
        finally:
            if task is not None:
                self._client_tasks.discard(task)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer: Peer | None = None
        try:
            remote = await handshake_as_responder(
                reader,
                writer,
                node_id=self.node_id,
                genesis_hash=self.genesis_hash,
                listen_port=self.port,
                timeout=self.config.handshake_timeout,
            )
            peer = Peer(
                reader,
                writer,
                remote.node_id,
                writer.get_extra_info("peername"),
                remote.listen_port,
            )
            if not self.book.add(peer):
                await peer.close()
                return
            await self._notify_connected(peer)
            await self._read_loop(peer)
        except (HandshakeError, ProtocolError, TimeoutError, ConnectionError, OSError):
            # A malformed or hostile peer is disconnected, never a crash.
            pass
        finally:
            if peer is not None:
                self.book.remove(peer)
            await self._close_writer(writer)

    def _spawn_reader(self, peer: Peer) -> None:
        task = asyncio.create_task(self._read_loop(peer))
        self._read_tasks.add(task)
        task.add_done_callback(self._read_tasks.discard)

    async def _read_loop(self, peer: Peer) -> None:
        try:
            while peer.alive:
                try:
                    msg = await read_message(peer.reader, self.config.idle_timeout)
                except (ProtocolError, TimeoutError, ConnectionError, OSError):
                    break
                if msg is None:
                    break  # clean EOF
                peer.last_seen = time.monotonic()
                await self._received.put(
                    ReceivedMessage(peer.node_id, msg.topic, msg.payload)
                )
        finally:
            self.book.remove(peer)
            await peer.close()

    async def broadcast(self, topic: str, payload: bytes) -> None:
        """Relay one message to every live peer, dropping dead ones."""
        for peer in self.book.all():
            await peer.send(topic, payload)
            if not peer.alive:
                self.book.remove(peer)

    async def send_to(self, node_id: bytes, topic: str, payload: bytes) -> bool:
        """Send one message to a specific peer; False if it is unknown/dead."""
        peer = self.book.get(node_id)
        if peer is None:
            return False
        await peer.send(topic, payload)
        if not peer.alive:
            self.book.remove(peer)
            return False
        return True

    def peer_count(self) -> int:
        return len(self.book)

    async def receive(self, timeout: float | None = None) -> ReceivedMessage | None:
        """Return the next received message.

        Blocks until a message arrives when ``timeout`` is None; otherwise
        returns None after ``timeout`` seconds with no message.
        """
        if timeout is None:
            return await self._received.get()
        try:
            return await asyncio.wait_for(self._received.get(), timeout)
        except TimeoutError:
            return None

    @staticmethod
    async def _close_writer(writer: asyncio.StreamWriter) -> None:
        try:
            writer.close()
        except (ConnectionError, OSError, RuntimeError):
            pass
