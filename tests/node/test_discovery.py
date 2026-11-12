"""Tests for peer discovery: AddressBook + GET_PEERS/PEERS codec + exchange."""

import asyncio
import struct
import time

import pytest

from kwartel.crypto.keys import generate_keypair
from kwartel.node.cluster import Cluster
from kwartel.node.discovery import (
    ADDRESS_BOOK_CAP,
    MAX_FAILURES,
    AddressBook,
    deserialize_peers,
    serialize_peers,
)

_U16 = struct.Struct("<H")
_U8 = struct.Struct("<B")


def _run(coro, timeout: float = 30.0):
    return asyncio.run(asyncio.wait_for(coro, timeout))


async def _wait_for(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


# -- PEERS wire codec (pure) ------------------------------------------------


def test_peers_codec_roundtrip():
    addrs = [("127.0.0.1", 9371), ("10.0.0.2", 9372), ("192.168.1.10", 9373)]
    assert deserialize_peers(serialize_peers(addrs)) == addrs


def test_peers_codec_empty():
    assert deserialize_peers(_U16.pack(0)) == []


def test_peers_codec_caps_count():
    addrs = [(f"127.0.0.{i}", 9000 + i) for i in range(1, 100)]
    encoded = serialize_peers(addrs)
    assert len(deserialize_peers(encoded)) == 64


def test_peers_codec_rejects_bad_count():
    with pytest.raises(ValueError):
        deserialize_peers(_U16.pack(65))


def test_peers_codec_rejects_zero_port():
    payload = _U16.pack(1) + _U8.pack(4) + b"host" + _U16.pack(0)
    with pytest.raises(ValueError):
        deserialize_peers(payload)


def test_peers_codec_rejects_oversized_host():
    # host_len=254 exceeds MAX_HOST_LEN
    payload = _U16.pack(1) + _U8.pack(254) + b"x" * 254 + _U16.pack(9371)
    with pytest.raises(ValueError):
        deserialize_peers(payload)


def test_peers_codec_rejects_truncation():
    payload = _U16.pack(2) + _U8.pack(4) + b"host" + _U16.pack(9371)
    with pytest.raises(ValueError):
        deserialize_peers(payload)


def test_peers_codec_rejects_trailing_bytes():
    payload = _U16.pack(1) + _U8.pack(4) + b"host" + _U16.pack(9371) + b"\x00"
    with pytest.raises(ValueError):
        deserialize_peers(payload)


# -- AddressBook (pure) -----------------------------------------------------


def test_address_book_add_dedup():
    book = AddressBook()
    assert book.add("127.0.0.1", 9371, "peer") is True
    assert book.add("127.0.0.1", 9371, "peer") is False  # duplicate
    assert len(book) == 1


def test_address_book_get_batch_excludes():
    book = AddressBook()
    for i in range(10):
        book.add(f"10.0.0.{i}", 9000 + i, "peer")
    batch = book.get_batch(3, exclude={("10.0.0.1", 9001), ("10.0.0.2", 9002)})
    assert len(batch) == 3
    assert len(set(batch)) == 3  # distinct
    assert ("10.0.0.1", 9001) not in batch
    assert ("10.0.0.2", 9002) not in batch


def test_address_book_mark_failed_drops():
    book = AddressBook()
    book.add("127.0.0.1", 9371, "peer")
    for _ in range(MAX_FAILURES - 1):
        book.mark_failed("127.0.0.1", 9371)
    assert len(book) == 1
    book.mark_failed("127.0.0.1", 9371)  # reaches threshold
    assert len(book) == 0


def test_address_book_mark_failed_keeps_configured():
    book = AddressBook()
    book.add("127.0.0.1", 9371, "configured")
    for _ in range(MAX_FAILURES + 3):
        book.mark_failed("127.0.0.1", 9371)
    assert len(book) == 1  # configured never dropped


def test_address_book_eviction(tmp_path):
    book = AddressBook(max_entries=4)
    # configured entries (never evicted)
    book.add("127.0.0.1", 9371, "configured")
    # peer entries (evictable, oldest first)
    book.add("127.0.0.2", 9372, "peer")
    book.add("127.0.0.3", 9373, "peer")
    book.add("127.0.0.4", 9374, "peer")
    # now full; adding a new peer evicts the oldest peer ("127.0.0.2")
    assert book.add("127.0.0.5", 9375, "peer") is True
    assert ("127.0.0.2", 9372) not in book.all()
    assert ("127.0.0.1", 9371) in book.all()  # configured survives


def test_address_book_persistence(tmp_path):
    path = tmp_path / "peers.json"
    book = AddressBook()
    book.add("127.0.0.1", 9371, "configured")
    book.add("10.0.0.2", 9372, "peer")
    book.mark_failed("10.0.0.2", 9372)
    book.save(path)

    loaded = AddressBook()
    loaded.load(path)
    assert set(loaded.all()) == {("127.0.0.1", 9371), ("10.0.0.2", 9372)}
    assert loaded.source_of("127.0.0.1", 9371) == "configured"


def test_address_book_corrupt_json(tmp_path):
    path = tmp_path / "peers.json"
    path.write_text("{ not valid json ")
    book = AddressBook()
    book.load(path)  # must not crash
    assert len(book) == 0


def test_peer_exchange_two_nodes(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            b = await cluster.add_node()
            await cluster.connect_mesh()
            assert await _wait_for(
                lambda: ("127.0.0.1", a.port) in b.addr_book.all()
                and ("127.0.0.1", b.port) in a.addr_book.all()
            )
            assert a.addr_book.source_of("127.0.0.1", b.port) == "observed"
            assert b.addr_book.source_of("127.0.0.1", a.port) == "observed"
        finally:
            await cluster.stop_all()

    _run(body())


def test_peers_message_validation(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            b = await cluster.add_node()
            await cluster.connect_mesh()
            assert await _wait_for(lambda: a.peer_count() == 1 and b.peer_count() == 1)

            # B sends a malformed PEERS payload (zero port); A must disconnect it.
            bad = _U16.pack(1) + _U8.pack(4) + b"host" + _U16.pack(0)
            await b.server.broadcast("PEERS", bad)
            assert await _wait_for(lambda: a.peer_count() == 0)

            # A is still alive and can still mine.
            miner = generate_keypair()
            await a.mine(miner.public)
            assert a.height() == 1
        finally:
            await cluster.stop_all()

    _run(body())


def test_three_node_discovery(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            b = await cluster.add_node()
            c = await cluster.add_node()
            # A connects to C first, then B, so B learns C's address from A.
            await a.connect("127.0.0.1", c.port)
            await a.connect("127.0.0.1", b.port)

            assert await _wait_for(lambda: ("127.0.0.1", c.port) in b.addr_book.all())
            assert b.addr_book.source_of("127.0.0.1", c.port) == "peer"
            # B auto-connects to C using only book data.
            assert await _wait_for(lambda: b.server.book.get(c.node_id) is not None)
        finally:
            await cluster.stop_all()

    _run(body())
