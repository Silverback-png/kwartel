"""Tests for kwartel.net.handshake."""

import asyncio

import pytest

from kwartel.net.framing import read_message, write_message
from kwartel.net.handshake import (
    PROTOCOL_MAGIC,
    PROTOCOL_VERSION,
    Handshake,
    HandshakeError,
    deserialize_handshake,
    handshake_as_connector,
    handshake_as_responder,
    serialize_handshake,
)

_NODE_A = bytes(range(32))
_NODE_B = bytes(range(32, 64))
_GENESIS = bytes(range(64, 96))
_OTHER_GENESIS = bytes([0xFF]) * 32


class _Box:
    def __init__(self) -> None:
        self.value = None
        self.error = None


async def _run_pair(connector_node_id, responder_node_id, connector_genesis, responder_genesis):
    """Run a full handshake over a real loopback connection.

    Returns (connector_remote, connector_error, responder_remote, responder_error).
    """
    box = _Box()
    done = asyncio.Event()

    async def handler(reader, writer):
        try:
            remote = await handshake_as_responder(
                reader,
                writer,
                node_id=responder_node_id,
                genesis_hash=responder_genesis,
                listen_port=9001,
                timeout=5,
            )
            box.value = remote
        except Exception as exc:  # noqa: BLE001 - capture any failure to assert on
            box.error = exc
        finally:
            done.set()
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        conn_remote = None
        conn_error = None
        try:
            conn_remote = await handshake_as_connector(
                reader,
                writer,
                node_id=connector_node_id,
                genesis_hash=connector_genesis,
                listen_port=9002,
                timeout=5,
            )
        except Exception as exc:  # noqa: BLE001
            conn_error = exc
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        await asyncio.wait_for(done.wait(), timeout=5)
        return conn_remote, conn_error, box.value, box.error
    finally:
        server.close()
        await server.wait_closed()


async def _bad_handshake_pair(connector_handshake, responder_node_id, responder_genesis):
    """Run a handshake where the connector sends ``connector_handshake``.

    Returns (responder_error, connector_received).  ``connector_received`` is
    None when the responder disconnected (clean EOF).
    """
    box = _Box()
    done = asyncio.Event()

    async def handler(reader, writer):
        try:
            remote = await handshake_as_responder(
                reader,
                writer,
                node_id=responder_node_id,
                genesis_hash=responder_genesis,
                listen_port=9001,
                timeout=5,
            )
            box.value = remote
        except Exception as exc:  # noqa: BLE001
            box.error = exc
        finally:
            done.set()
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        await write_message(
            writer, "HANDSHAKE", serialize_handshake(connector_handshake), timeout=5
        )
        received = await read_message(reader, timeout=5)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        await asyncio.wait_for(done.wait(), timeout=5)
        return box.error, received
    finally:
        server.close()
        await server.wait_closed()


def test_handshake_happy_path():
    async def body():
        conn, conn_err, resp, resp_err = await _run_pair(
            _NODE_A, _NODE_B, _GENESIS, _GENESIS
        )
        assert conn_err is None and resp_err is None
        assert conn.node_id == _NODE_B  # connector learned responder's id
        assert resp.node_id == _NODE_A  # responder learned connector's id
        assert conn.genesis_hash == _GENESIS
        assert conn.listen_port == 9001
        assert resp.listen_port == 9002

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_handshake_serialize_roundtrip():
    h = Handshake(PROTOCOL_MAGIC, PROTOCOL_VERSION, _NODE_A, _GENESIS, 9371)
    assert deserialize_handshake(serialize_handshake(h)) == h


def test_deserialize_rejects_truncated():
    h = Handshake(PROTOCOL_MAGIC, PROTOCOL_VERSION, _NODE_A, _GENESIS, 1)
    with pytest.raises(HandshakeError):
        deserialize_handshake(serialize_handshake(h)[:-1])


def test_deserialize_rejects_trailing_bytes():
    h = Handshake(PROTOCOL_MAGIC, PROTOCOL_VERSION, _NODE_A, _GENESIS, 1)
    with pytest.raises(HandshakeError):
        deserialize_handshake(serialize_handshake(h) + b"\x00")


def test_magic_mismatch_disconnect():
    async def body():
        bad = Handshake(0xDEADBEEF, PROTOCOL_VERSION, _NODE_A, _GENESIS, 1)
        resp_err, received = await _bad_handshake_pair(bad, _NODE_B, _GENESIS)
        assert isinstance(resp_err, HandshakeError)
        assert received is None  # responder disconnected

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_version_mismatch_disconnect():
    async def body():
        bad = Handshake(PROTOCOL_MAGIC, PROTOCOL_VERSION + 1, _NODE_A, _GENESIS, 1)
        resp_err, received = await _bad_handshake_pair(bad, _NODE_B, _GENESIS)
        assert isinstance(resp_err, HandshakeError)
        assert received is None

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_genesis_mismatch_disconnect():
    async def body():
        bad = Handshake(PROTOCOL_MAGIC, PROTOCOL_VERSION, _NODE_A, _OTHER_GENESIS, 1)
        resp_err, received = await _bad_handshake_pair(bad, _NODE_B, _GENESIS)
        assert isinstance(resp_err, HandshakeError)
        assert received is None

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_self_connect_disconnect():
    async def body():
        bad = Handshake(PROTOCOL_MAGIC, PROTOCOL_VERSION, _NODE_B, _GENESIS, 1)
        resp_err, received = await _bad_handshake_pair(bad, _NODE_B, _GENESIS)
        assert isinstance(resp_err, HandshakeError)
        assert received is None

    asyncio.run(asyncio.wait_for(body(), timeout=15))
