"""Protocol magic + version exchange that precedes all other traffic.

Before any other message flows, a connector sends HANDSHAKE and the responder
replies HANDSHAKE_ACK.  Both carry magic, version, node identity, the pinned
genesis hash, and the sender's listen port.  Both sides validate the remote
payload and disconnect on any mismatch.

The genesis hash is what makes the transport refuse to talk to peers on a
different chain: a node on another network has a different genesis and must not
be gossiped with.  Magic is a cheap first filter against accidental non-Kwartel
connections.  See ``kwartel/net/README.md``.
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass

from kwartel.net.framing import read_message, write_message

_U32 = struct.Struct("<I")
_U16 = struct.Struct("<H")

PROTOCOL_MAGIC = 0x4B575431  # "KWT1"
PROTOCOL_VERSION = 1

_NODE_ID_LEN = 32
_GENESIS_LEN = 32


class HandshakeError(Exception):
    """Raised when a handshake is malformed or fails validation."""


@dataclass(frozen=True)
class Handshake:
    """The canonical handshake payload exchanged in both directions."""

    magic: int
    version: int
    node_id: bytes        # 32 bytes
    genesis_hash: bytes   # 32 bytes
    listen_port: int      # u16


def _encode_bytes(data: bytes) -> bytes:
    """Length-prefixed byte string: u32 LE length + raw bytes."""
    return _U32.pack(len(data)) + data


def serialize_handshake(h: Handshake) -> bytes:
    """Return the canonical, length-prefixed serialization of ``h``.

    Layout: magic(u32 LE), version(u32 LE), node_id(len-prefixed),
    genesis_hash(len-prefixed), listen_port(u16 LE).
    """
    return (
        _U32.pack(h.magic)
        + _U32.pack(h.version)
        + _encode_bytes(h.node_id)
        + _encode_bytes(h.genesis_hash)
        + _U16.pack(h.listen_port)
    )


def deserialize_handshake(data: bytes) -> Handshake:
    """Reconstruct a ``Handshake`` from ``serialize_handshake`` output.

    Never trusts input: raises ``HandshakeError`` on truncation, bad field
    lengths, or trailing garbage.
    """
    try:
        magic = _U32.unpack_from(data, 0)[0]
        version = _U32.unpack_from(data, 4)[0]
        off = 8
        node_id_len = _U32.unpack_from(data, off)[0]
        off += 4
        node_id = data[off : off + node_id_len]
        off += node_id_len
        genesis_len = _U32.unpack_from(data, off)[0]
        off += 4
        genesis_hash = data[off : off + genesis_len]
        off += genesis_len
        listen_port = _U16.unpack_from(data, off)[0]
        off += 2
    except (struct.error, IndexError) as exc:
        raise HandshakeError("malformed handshake") from exc

    if len(node_id) != _NODE_ID_LEN:
        raise HandshakeError(f"node_id length {len(node_id)}, expected {_NODE_ID_LEN}")
    if len(genesis_hash) != _GENESIS_LEN:
        raise HandshakeError(
            f"genesis_hash length {len(genesis_hash)}, expected {_GENESIS_LEN}"
        )
    if off != len(data):
        raise HandshakeError("trailing bytes in handshake")

    return Handshake(
        magic=magic,
        version=version,
        node_id=node_id,
        genesis_hash=genesis_hash,
        listen_port=listen_port,
    )


def validate_handshake(
    h: Handshake, our_node_id: bytes, our_genesis_hash: bytes
) -> None:
    """Validate a remote handshake against our identity and chain.

    Raises ``HandshakeError`` on any mismatch.  Phase 2 uses an exact
    same-version policy: the versions must match exactly.
    """
    if h.magic != PROTOCOL_MAGIC:
        raise HandshakeError(f"magic mismatch: {h.magic:#x}")
    if h.version != PROTOCOL_VERSION:
        raise HandshakeError(f"version mismatch: {h.version}")
    if h.genesis_hash != our_genesis_hash:
        raise HandshakeError("genesis hash mismatch")
    if h.node_id == our_node_id:
        raise HandshakeError("self-connect: remote node_id equals our own")


def _ours(node_id: bytes, genesis_hash: bytes, listen_port: int) -> Handshake:
    return Handshake(
        magic=PROTOCOL_MAGIC,
        version=PROTOCOL_VERSION,
        node_id=node_id,
        genesis_hash=genesis_hash,
        listen_port=listen_port,
    )


async def handshake_as_connector(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    node_id: bytes,
    genesis_hash: bytes,
    listen_port: int,
    timeout: float,
) -> Handshake:
    """Perform the outbound half of the handshake; return the remote's info."""
    await write_message(
        writer,
        "HANDSHAKE",
        serialize_handshake(_ours(node_id, genesis_hash, listen_port)),
        timeout,
    )
    reply = await read_message(reader, timeout)
    if reply is None or reply.topic != "HANDSHAKE_ACK":
        raise HandshakeError("expected HANDSHAKE_ACK")
    remote = deserialize_handshake(reply.payload)
    validate_handshake(remote, node_id, genesis_hash)
    return remote


async def handshake_as_responder(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    node_id: bytes,
    genesis_hash: bytes,
    listen_port: int,
    timeout: float,
) -> Handshake:
    """Perform the inbound half of the handshake; return the remote's info."""
    request = await read_message(reader, timeout)
    if request is None or request.topic != "HANDSHAKE":
        raise HandshakeError("expected HANDSHAKE")
    remote = deserialize_handshake(request.payload)
    validate_handshake(remote, node_id, genesis_hash)
    await write_message(
        writer,
        "HANDSHAKE_ACK",
        serialize_handshake(_ours(node_id, genesis_hash, listen_port)),
        timeout,
    )
    return remote
