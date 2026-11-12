"""Tests for kwartel.net.server."""

import asyncio
import struct
import time

import pytest

from kwartel.net.config import NetConfig
from kwartel.net.framing import MAX_PAYLOAD
from kwartel.net.handshake import HandshakeError
from kwartel.net.peer import Peer
from kwartel.net.server import PeerBook, Server

_U32 = struct.Struct("<I")

_NODE_A = bytes(range(32))
_NODE_B = bytes(range(32, 64))
_NODE_C = bytes(range(64, 96))
_GENESIS = bytes(range(96, 128))


def _server(node_id: bytes, **kwargs) -> Server:
    cfg = {"port": 0, "handshake_timeout": 3.0, "idle_timeout": 5.0}
    cfg.update(kwargs)
    return Server(NetConfig(**cfg), node_id, _GENESIS)


async def _until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met within timeout")


def test_peerbook_add_remove_get():
    book = PeerBook(max_peers=2)
    p1 = Peer(None, None, _NODE_A, ("127.0.0.1", 1))
    p2 = Peer(None, None, _NODE_B, ("127.0.0.1", 2))
    assert book.add(p1) is True
    assert book.add(Peer(None, None, _NODE_A, ("127.0.0.1", 3))) is False  # duplicate
    assert book.add(p2) is True
    assert book.add(Peer(None, None, _NODE_C, ("127.0.0.1", 4))) is False  # full
    assert book.get(_NODE_A) is p1
    assert book.all() == [p1, p2]
    book.remove(p1)
    assert book.get(_NODE_A) is None
    assert len(book) == 1


def test_handshake_success_both_ways():
    async def body():
        a = _server(_NODE_A)
        b = _server(_NODE_B)
        await a.start()
        await b.start()
        try:
            peer = await a.connect_peer("127.0.0.1", b.port)
            await _until(lambda: b.peer_count() == 1)
            assert a.peer_count() == 1
            assert peer.node_id == _NODE_B
            assert b.book.get(_NODE_A) is not None
        finally:
            await a.stop()
            await b.stop()

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_broadcast_reaches_all_peers():
    async def body():
        a = _server(_NODE_A)
        b = _server(_NODE_B)
        await a.start()
        await b.start()
        try:
            await a.connect_peer("127.0.0.1", b.port)
            await _until(lambda: b.peer_count() == 1)
            await b.broadcast("DATA", b"hello")
            got = await a.receive(timeout=5)
            assert got is not None
            assert got.node_id == _NODE_B
            assert got.topic == "DATA"
            assert got.payload == b"hello"
        finally:
            await a.stop()
            await b.stop()

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_send_to_known_and_unknown_peer():
    async def body():
        a = _server(_NODE_A)
        b = _server(_NODE_B)
        await a.start()
        await b.start()
        try:
            peer = await a.connect_peer("127.0.0.1", b.port)
            await _until(lambda: b.peer_count() == 1)
            assert await a.send_to(peer.node_id, "PING", b"x") is True
            got = await b.receive(timeout=5)
            assert got is not None and got.topic == "PING" and got.node_id == _NODE_A
            assert await a.send_to(_NODE_C, "DATA", b"x") is False
        finally:
            await a.stop()
            await b.stop()

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_dead_peer_cleanup():
    async def body():
        a = _server(_NODE_A)
        b = _server(_NODE_B)
        await a.start()
        await b.start()
        try:
            await a.connect_peer("127.0.0.1", b.port)
            await _until(lambda: b.peer_count() == 1)
            b_peer = b.book.get(_NODE_A)
            await b_peer.close()
            await _until(lambda: a.peer_count() == 0)
        finally:
            await a.stop()
            await b.stop()

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_oversized_message_disconnect():
    async def body():
        a = _server(_NODE_A)
        b = _server(_NODE_B)
        await a.start()
        await b.start()
        try:
            peer = await a.connect_peer("127.0.0.1", b.port)
            await _until(lambda: b.peer_count() == 1)
            # A sends a raw oversized frame, bypassing write_message's cap.
            peer.writer.write(_U32.pack(MAX_PAYLOAD + 1))
            await peer.writer.drain()
            await _until(lambda: a.peer_count() == 0 and b.peer_count() == 0)
        finally:
            await a.stop()
            await b.stop()

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_handshake_timeout_disconnect():
    async def body():
        async def silent(reader, writer):
            try:
                await asyncio.sleep(30)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

        server = await asyncio.start_server(silent, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        node = _server(_NODE_A, handshake_timeout=0.3)
        await node.start()
        try:
            with pytest.raises((HandshakeError, TimeoutError)):
                await node.connect_peer("127.0.0.1", port)
            assert node.peer_count() == 0
        finally:
            await node.stop()
            server.close()
            await server.wait_closed()

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_three_nodes_exchange():
    async def body():
        a = _server(_NODE_A)
        b = _server(_NODE_B)
        c = _server(_NODE_C)
        await a.start()
        await b.start()
        await c.start()
        try:
            # Mesh A<->B<->C via direct connections through B.
            await a.connect_peer("127.0.0.1", b.port)
            await c.connect_peer("127.0.0.1", b.port)
            await _until(lambda: b.peer_count() == 2)
            await b.broadcast("DATA", b"mesh test")
            got_a = await a.receive(timeout=5)
            got_c = await c.receive(timeout=5)
            assert got_a is not None and got_a.payload == b"mesh test"
            assert got_c is not None and got_c.payload == b"mesh test"
        finally:
            await a.stop()
            await b.stop()
            await c.stop()

    asyncio.run(asyncio.wait_for(body(), timeout=15))
