"""Tests for kwartel.crypto.base58."""

from kwartel.crypto.base58 import b58check_decode, b58check_encode, decode, encode


def test_base58_roundtrip():
    data = b"\x00\x01\x02\x03hello"
    assert decode(encode(data)) == data


def test_base58_leading_zeros_preserved():
    data = b"\x00\x00\x00abc"
    encoded = encode(data)
    assert encoded.startswith("111")
    assert decode(encoded) == data


def test_base58_known_vector():
    # The classic Bitcoin test vector for "hello world".
    assert encode(b"hello world") == "StV1DL6CwTryKyV"


def test_b58check_roundtrip():
    payload = b"\x00" + bytes(range(32))
    encoded = b58check_encode(payload)
    assert b58check_decode(encoded) == payload


def test_b58check_invalid_checksum_fails():
    payload = b"\x00" + bytes(range(32))
    encoded = b58check_encode(payload)
    # Flip a character in the middle of the encoded string.
    mutated = encoded[:5] + ("2" if encoded[5] != "2" else "3") + encoded[6:]
    try:
        b58check_decode(mutated)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for invalid checksum")


def test_b58check_leading_zeros():
    payload = b"\x00\x00\x00\x01\x02\x03"
    encoded = b58check_encode(payload)
    assert b58check_decode(encoded) == payload
