"""Tests for kwartel.net.framing."""

import asyncio
import struct

import pytest

from kwartel.net.framing import (
    MAX_PAYLOAD,
    TOPICS,
    Message,
    ProtocolError,
    read_message,
    write_message,
)

_U32 = struct.Struct("<I")
_U16 = struct.Struct("<H")


def _reader_with(data: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


class _FakeWriter:
    """Captures written bytes; drain() is a no-op."""

    def __init__(self) -> None:
        self.data = b""

    def write(self, data: bytes) -> None:
        self.data += data

    async def drain(self) -> None:
        pass


async def _echo_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    msg = await read_message(reader, timeout=5)
    await write_message(writer, msg.topic, msg.payload, timeout=5)
    writer.close()
    await writer.wait_closed()


def test_roundtrip_all_topics():
    async def body():
        server = await asyncio.start_server(_echo_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            for topic in TOPICS:
                payload = f"payload-{topic}".encode()
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                await write_message(writer, topic, payload, timeout=5)
                msg = await read_message(reader, timeout=5)
                assert msg == Message(topic=topic, payload=payload)
                writer.close()
                await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_write_message_frames_correctly():
    async def body():
        writer = _FakeWriter()
        await write_message(writer, "DATA", b"abc", timeout=5)
        assert writer.data == _U32.pack(3) + _U16.pack(TOPICS["DATA"]) + b"abc"

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_oversized_length_rejected():
    async def body():
        reader = _reader_with(_U32.pack(MAX_PAYLOAD + 1))
        with pytest.raises(ProtocolError):
            await read_message(reader, timeout=5)

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_truncated_payload_rejected():
    async def body():
        reader = _reader_with(_U32.pack(5) + b"ab")  # declares 5 bytes, sends 2
        with pytest.raises(ProtocolError):
            await read_message(reader, timeout=5)

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_unknown_topic_rejected():
    async def body():
        reader = _reader_with(_U32.pack(3) + _U16.pack(0xFFFF) + b"abc")
        with pytest.raises(ProtocolError):
            await read_message(reader, timeout=5)

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_eof_returns_none():
    async def body():
        reader = asyncio.StreamReader()
        reader.feed_eof()
        assert await read_message(reader, timeout=5) is None

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_unknown_topic_write_rejected():
    async def body():
        with pytest.raises(ProtocolError):
            await write_message(_FakeWriter(), "NOT_A_TOPIC", b"x", timeout=5)

    asyncio.run(asyncio.wait_for(body(), timeout=15))


def test_oversized_write_rejected():
    async def body():
        with pytest.raises(ProtocolError):
            await write_message(_FakeWriter(), "DATA", b"x" * (MAX_PAYLOAD + 1), timeout=5)

    asyncio.run(asyncio.wait_for(body(), timeout=15))
