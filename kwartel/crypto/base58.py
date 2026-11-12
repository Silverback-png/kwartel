"""Base58 and Base58Check encoding/decoding for Kwartel addresses."""

from __future__ import annotations

import hashlib

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ALPHABET_INDEX = {char: idx for idx, char in enumerate(ALPHABET)}
BASE = len(ALPHABET)


def encode(data: bytes) -> str:
    """Encode raw ``data`` as Base58 (no checksum)."""
    if not data:
        return ""

    # Count and preserve leading zero bytes, which become '1' characters.
    leading_zeros = 0
    for byte in data:
        if byte == 0:
            leading_zeros += 1
        else:
            break

    # Convert the remaining bytes to a big integer and encode in base 58.
    value = int.from_bytes(data, byteorder="big")
    encoded = ""
    while value > 0:
        value, remainder = divmod(value, BASE)
        encoded = ALPHABET[remainder] + encoded

    return "1" * leading_zeros + encoded


def decode(text: str) -> bytes:
    """Decode a Base58 string (no checksum) back to raw bytes."""
    if not text:
        return b""

    leading_zeros = 0
    for char in text:
        if char == "1":
            leading_zeros += 1
        else:
            break

    value = 0
    for char in text:
        if char not in ALPHABET_INDEX:
            raise ValueError(f"Invalid Base58 character: {char!r}")
        value = value * BASE + ALPHABET_INDEX[char]

    # Convert the integer back to bytes, preserving the original length.
    if value == 0:
        return b"\x00" * leading_zeros

    byte_length = (value.bit_length() + 7) // 8
    body = value.to_bytes(byte_length, byteorder="big")
    return b"\x00" * leading_zeros + body


def _checksum(payload: bytes) -> bytes:
    """Return the first 4 bytes of double-SHA256 of ``payload``."""
    return hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]


def b58check_encode(payload: bytes) -> str:
    """Base58Check-encode ``payload`` (payload + 4-byte checksum)."""
    return encode(payload + _checksum(payload))


def b58check_decode(text: str) -> bytes:
    """Base58Check-decode ``text`` and return the payload.

    Raises ``ValueError`` if the checksum is invalid or the text is malformed.
    """
    raw = decode(text)
    if len(raw) < 4:
        raise ValueError("Base58Check data too short for checksum")
    payload, checksum = raw[:-4], raw[-4:]
    if checksum != _checksum(payload):
        raise ValueError("Base58Check checksum mismatch")
    return payload
