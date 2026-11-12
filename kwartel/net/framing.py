"""Length-prefixed binary framing for the Kwartel wire protocol.

Every message on the wire is:

    [u32 LE payload_len][u16 LE topic_id][payload]

The length prefix lets a reader allocate exactly the right number of bytes and
detect truncation immediately, without scanning for a delimiter character that
might itself appear inside a binary payload.  See ``kwartel/net/README.md``.
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass

_U32 = struct.Struct("<I")
_U16 = struct.Struct("<H")

# Blocks are small in Phase 2, but cap inbound payloads anyway so a hostile peer
# cannot make us allocate unbounded memory.
MAX_PAYLOAD = 8 * 1024 * 1024  # 8 MiB

# Topic ids are fixed in this single dict; no magic numbers scattered in code.
TOPICS = {
    "HANDSHAKE": 1,
    "HANDSHAKE_ACK": 2,
    "PING": 3,
    "PONG": 4,
    "DATA": 5,
    "BLOCK": 6,
    "TX": 7,
    "INV_BLOCK": 8,
    "GET_BLOCK": 9,
    "GET_STATUS": 10,
    "STATUS": 11,
    "GET_PEERS": 12,
    "PEERS": 13,
}

_TOPIC_NAMES = {topic_id: name for name, topic_id in TOPICS.items()}

DEFAULT_IDLE_TIMEOUT = 30.0


class ProtocolError(Exception):
    """Raised when a peer sends bytes that violate the wire protocol."""


@dataclass(frozen=True)
class Message:
    """A decoded inbound message: a topic name plus its raw payload."""

    topic: str
    payload: bytes


async def _read_exact(
    reader: asyncio.StreamReader, size: int, timeout: float
) -> bytes:
    """Read exactly ``size`` bytes, bounded by ``timeout`` so dead peers cannot
    hold resources forever."""
    return await asyncio.wait_for(reader.readexactly(size), timeout)


async def read_message(
    reader: asyncio.StreamReader, timeout: float = DEFAULT_IDLE_TIMEOUT
) -> Message | None:
    """Read one framed message from ``reader``.

    Returns ``None`` on a clean EOF (no bytes read).  Raises ``ProtocolError``
    for any malformed input: an oversized length, an unknown topic id, or a
    truncated frame.  Raises ``TimeoutError`` if the read stalls beyond
    ``timeout``.
    """
    try:
        length_bytes = await _read_exact(reader, 4, timeout)
    except asyncio.IncompleteReadError as exc:
        if not exc.partial:
            return None  # clean EOF before the length prefix
        raise ProtocolError("truncated length prefix") from exc

    (payload_len,) = _U32.unpack(length_bytes)
    if payload_len > MAX_PAYLOAD:
        raise ProtocolError(f"payload length {payload_len} exceeds cap {MAX_PAYLOAD}")

    try:
        topic_bytes = await _read_exact(reader, 2, timeout)
        (topic_id,) = _U16.unpack(topic_bytes)
        topic = _TOPIC_NAMES.get(topic_id)
        if topic is None:
            raise ProtocolError(f"unknown topic id {topic_id}")
        payload = await _read_exact(reader, payload_len, timeout)
    except asyncio.IncompleteReadError as exc:
        raise ProtocolError("truncated message") from exc

    return Message(topic=topic, payload=payload)


async def write_message(
    writer: asyncio.StreamWriter,
    topic: str,
    payload: bytes,
    timeout: float = DEFAULT_IDLE_TIMEOUT,
) -> None:
    """Write one framed message to ``writer``."""
    if topic not in TOPICS:
        raise ProtocolError(f"unknown topic {topic!r}")
    if len(payload) > MAX_PAYLOAD:
        raise ProtocolError(f"payload length {len(payload)} exceeds cap {MAX_PAYLOAD}")

    frame = _U32.pack(len(payload)) + _U16.pack(TOPICS[topic]) + payload
    writer.write(frame)
    await asyncio.wait_for(writer.drain(), timeout)
