"""NetNode: FullNode logic over the TCP transport, with discovery and IBD.

The chain and mempool remain the single source of truth; validation is imported
from ``kwartel.blockchain`` and ``kwartel.transaction``.  Message handling is
shared with the in-memory ``FullNode`` via ``kwartel.node.gossip``.  Peer
discovery lives in ``kwartel.node.discovery``; initial download in
``kwartel.node.sync``.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import struct
import time
from pathlib import Path

from kwartel.blockchain.block import Block, block_hash
from kwartel.blockchain.chain import Chain
from kwartel.blockchain.genesis import GENESIS_HASH
from kwartel.blockchain.persistence import BlockStore, serialize_block
from kwartel.net.config import NetConfig
from kwartel.net.server import Server
from kwartel.node.discovery import (
    DISCOVERY_INTERVAL,
    MAX_NEW_CONNECTIONS_PER_BATCH,
    MAX_PEERS_PER_MESSAGE,
    AddressBook,
    deserialize_peers,
    serialize_peers,
)
from kwartel.node.gossip import handle_message
from kwartel.node.miner import build_and_add_block
from kwartel.node.sync import REQUEST_TIMEOUT, SyncPlanner
from kwartel.transaction.mempool import Mempool
from kwartel.transaction.model import Transaction, serialize_tx

_U64 = struct.Struct("<Q")


class NetNode:
    """A full node whose gossip, discovery, and sync travel over TCP."""

    def __init__(
        self,
        node_id_str: str,
        data_dir: Path,
        listen_port: int | None = None,
        *,
        configured_peers: list | None = None,
        discovery_interval: float = DISCOVERY_INTERVAL,
        sync_request_timeout: float = REQUEST_TIMEOUT,
        sync_tick: float = 1.0,
    ) -> None:
        self.node_id_str = node_id_str
        self.node_id = hashlib.sha256(node_id_str.encode()).digest()
        self.store = BlockStore(data_dir)
        self.chain = Chain(self.store)
        self.mempool = Mempool()
        self._pending: dict = {}
        self.peer_statuses: dict[bytes, tuple[int, str]] = {}

        self.addr_book = AddressBook()
        self.sync = SyncPlanner(request_timeout=sync_request_timeout)
        self._peers_path = Path(data_dir).with_suffix(".peers.json")
        self._configured_peers = list(configured_peers or [])
        self._discovery_interval = discovery_interval
        self._sync_tick = sync_tick
        self._synced_logged = False

        self.server = Server(
            NetConfig(port=listen_port or 0),
            self.node_id,
            bytes.fromhex(GENESIS_HASH),
        )
        self.server.on_peer_connected = self._on_peer_connected

        self._outgoing: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
        self._connector_tasks: set[asyncio.Task] = set()
        self._reader_task: asyncio.Task | None = None
        self._writer_task: asyncio.Task | None = None
        self._maintenance_task: asyncio.Task | None = None

    @property
    def port(self) -> int:
        return self.server.port

    async def start(self) -> None:
        self.addr_book.load(self._peers_path)
        for host, port in self._configured_peers:
            self.addr_book.add(host, port, "configured")
        await self.server.start()
        self._reader_task = asyncio.create_task(self._reader_loop())
        self._writer_task = asyncio.create_task(self._writer_loop())
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        await self._bootstrap()

    async def stop(self) -> None:
        for task in (self._reader_task, self._writer_task, self._maintenance_task):
            if task is not None:
                task.cancel()
        pending = [
            t
            for t in (self._reader_task, self._writer_task, self._maintenance_task)
            if t is not None and not t.done()
        ]
        if pending:
            # Bounded: never hang on a task that ignores cancellation.
            await asyncio.wait(pending, timeout=2.0)
        self._reader_task = None
        self._writer_task = None
        self._maintenance_task = None
        # Background connector tasks may be stuck in an outbound TCP connect;
        # cancel them fire-and-forget rather than awaiting them.
        for task in list(self._connector_tasks):
            task.cancel()
        self._connector_tasks.clear()
        await self.server.stop()
        self.addr_book.save(self._peers_path)
        self.store.close()

    async def connect(self, host: str, port: int):
        """Outbound handshake; discovery/status exchange happens via the hook."""
        return await self.server.connect_peer(host, port)

    # -- public API ---------------------------------------------------------

    def submit_tx(self, tx: Transaction) -> bool:
        if self.mempool.accept(tx, self.chain.utxo_set()):
            self._outgoing.put_nowait(("TX", serialize_tx(tx, include_signatures=True)))
            return True
        return False

    def height(self) -> int:
        return self.chain.height()

    def tip_hash(self) -> str:
        return block_hash(self.chain.tip().header)

    def balance(self, pubkey: bytes) -> int:
        return self.chain.balance(pubkey)

    def peer_count(self) -> int:
        return self.server.peer_count()

    def announce_tip(self) -> None:
        self._outgoing.put_nowait(("INV_BLOCK", bytes.fromhex(self.tip_hash())))

    async def mine(self, coinbase_pubkey: bytes) -> Block | None:
        block = build_and_add_block(self.chain, self.mempool, coinbase_pubkey)
        if block is not None:
            await self.server.broadcast("BLOCK", serialize_block(block))
        return block

    async def _reader_loop(self) -> None:
        while True:
            msg = await self.server.receive()
            try:
                await self._dispatch(msg.node_id, msg.topic, msg.payload)
            except Exception:
                # A hostile peer is handled inside _dispatch; anything else must
                # never crash the node.
                pass

    async def _writer_loop(self) -> None:
        while True:
            topic, payload = await self._outgoing.get()
            await self.server.broadcast(topic, payload)

    async def _maintenance_loop(self) -> None:
        next_discovery = time.monotonic() + self._discovery_interval
        while True:
            await asyncio.sleep(self._sync_tick)
            for _block_hash, peer_id in self.sync.expire():
                self.peer_statuses.pop(peer_id, None)
            await self._drive_sync()
            now = time.monotonic()
            if now >= next_discovery:
                next_discovery = now + self._discovery_interval
                await self._discovery_tick()

    # -- discovery ----------------------------------------------------------

    async def _on_peer_connected(self, peer) -> None:
        """Called (both directions) after a handshake completes."""
        self.addr_book.add(peer.host, peer.listen_port, "observed")
        await self.server.send_to(peer.node_id, "GET_STATUS", b"")
        await self.server.send_to(peer.node_id, "GET_PEERS", b"")

    async def _discovery_tick(self) -> None:
        peers = self.server.book.all()
        if not peers:
            return
        await self.server.send_to(random.choice(peers).node_id, "GET_PEERS", b"")

    def _self_addr(self) -> tuple[str, int]:
        return (self.server.config.host, self.port)

    async def _bootstrap(self) -> None:
        """Connect out to known peers on startup (best-effort)."""
        self_addr = self._self_addr()
        for host, port in self.addr_book.all():
            if (host, port) == self_addr:
                continue
            if self.server.peer_count() >= self.server.config.max_peers:
                break
            try:
                await self.server.connect_peer(host, port)
            except Exception:
                self.addr_book.mark_failed(host, port)

    async def _connect_to_new_peers(
        self, limit: int = MAX_NEW_CONNECTIONS_PER_BATCH
    ) -> None:
        self_addr = self._self_addr()
        connected = {
            (p.host, p.listen_port)
            for p in self.server.book.all()
            if p.listen_port is not None
        }
        candidates = [
            addr
            for addr in self.addr_book.all()
            if addr != self_addr and addr not in connected
        ]
        for host, port in candidates[:limit]:
            if self.server.peer_count() >= self.server.config.max_peers:
                break
            try:
                await self.server.connect_peer(host, port)
            except Exception:
                self.addr_book.mark_failed(host, port)

    async def _send_peers(self, requester: bytes) -> None:
        exclude = {self._self_addr()}
        requester_peer = self.server.book.get(requester)
        if requester_peer is not None and requester_peer.listen_port is not None:
            exclude.add((requester_peer.host, requester_peer.listen_port))
        batch = self.addr_book.get_batch(MAX_PEERS_PER_MESSAGE, exclude)
        await self.server.send_to(requester, "PEERS", serialize_peers(batch))

    async def _handle_peers(self, payload: bytes) -> None:
        addrs = deserialize_peers(payload)  # ValueError on malformed
        for host, port in addrs:
            self.addr_book.add(host, port, "peer")
        # Connect out in the background: never block the reader loop on a
        # (potentially slow or stuck) outbound TCP connect.
        self._spawn_connector(self._connect_to_new_peers())

    def _spawn_connector(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._connector_tasks.add(task)
        task.add_done_callback(self._connector_tasks.discard)

    async def _drive_sync(self) -> None:
        if (
            not self._synced_logged
            and self.peer_statuses
            and self.sync.is_done(self.height(), self.tip_hash(), self.peer_statuses)
        ):
            self._synced_logged = True
            if self.height() > 0:
                print(f"[{self.node_id_str}] IBD complete at height {self.height()}")
        for peer_id, block_hash in self.sync.plan(
            self.height(), self.peer_statuses, self.store.has_block
        ):
            await self.server.send_to(peer_id, "GET_BLOCK", bytes.fromhex(block_hash))

    async def _dispatch(self, sender: bytes, topic: str, payload: bytes) -> None:
        try:
            if topic == "GET_STATUS":
                await self.server.send_to(sender, "STATUS", self._status_bytes())
                return
            if topic == "STATUS":
                height, tip = self._parse_status(payload)
                self.peer_statuses[sender] = (height, tip)
                await self._drive_sync()
                return
            if topic == "GET_PEERS":
                await self._send_peers(sender)
                return
            if topic == "PEERS":
                await self._handle_peers(payload)
                return
            for out_topic, out_payload in handle_message(
                self.store, self.chain, self.mempool, self._pending, topic, payload
            ):
                await self.server.broadcast(out_topic, out_payload)
            if topic == "BLOCK":
                await self._drive_sync()
        except (struct.error, IndexError, ValueError):
            # Malformed deserialize = protocol garbage: disconnect that peer.
            await self._disconnect(sender)

    def _parse_status(self, payload: bytes) -> tuple[int, str]:
        (height,) = _U64.unpack_from(payload, 0)
        tip_bytes = payload[8:40]
        if len(tip_bytes) != 32:
            raise ValueError("STATUS tip hash length != 32")
        return height, tip_bytes.hex()

    def _status_bytes(self) -> bytes:
        return _U64.pack(self.height()) + bytes.fromhex(self.tip_hash())

    async def _disconnect(self, node_id: bytes) -> None:
        peer = self.server.book.get(node_id)
        if peer is not None:
            self.server.book.remove(peer)
            await peer.close()
