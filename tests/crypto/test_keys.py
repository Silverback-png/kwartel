"""Tests for kwartel.crypto.keys."""

from kwartel.crypto.keys import (
    address,
    derive_public,
    generate_keypair,
    hash_bytes,
    sha256_hex,
    sign,
    validate_address,
    verify,
)


def test_generate_keypair_returns_distinct_pairs():
    kp1 = generate_keypair()
    kp2 = generate_keypair()
    assert kp1.secret != kp2.secret
    assert kp1.public != kp2.public


def test_public_key_derivable_from_secret():
    kp = generate_keypair()
    assert derive_public(kp.secret) == kp.public


def test_sign_and_verify_roundtrip():
    kp = generate_keypair()
    message = b"hello kwartel"
    signature = sign(kp.secret, message)
    assert verify(kp.public, message, signature) is True


def test_verify_fails_on_tampered_message():
    kp = generate_keypair()
    message = b"hello kwartel"
    signature = sign(kp.secret, message)
    tampered = bytearray(message)
    tampered[0] ^= 0x01
    assert verify(kp.public, bytes(tampered), signature) is False


def test_verify_fails_on_wrong_key():
    kp = generate_keypair()
    other = generate_keypair()
    message = b"hello kwartel"
    signature = sign(kp.secret, message)
    assert verify(other.public, message, signature) is False


def test_verify_fails_on_tampered_signature():
    kp = generate_keypair()
    message = b"hello kwartel"
    signature = bytearray(sign(kp.secret, message))
    signature[0] ^= 0x01
    assert verify(kp.public, message, bytes(signature)) is False


def test_signature_is_64_bytes():
    kp = generate_keypair()
    message = b"hello kwartel"
    signature = sign(kp.secret, message)
    assert len(signature) == 64


def test_sign_is_deterministic():
    kp = generate_keypair()
    message = b"hello kwartel"
    sig1 = sign(kp.secret, message)
    sig2 = sign(kp.secret, message)
    assert sig1 == sig2


def test_sha256_empty_vector():
    assert (
        sha256_hex(b"")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_hash_bytes_returns_32_bytes():
    assert len(hash_bytes(b"kwartel")) == 32


def test_sha256_hex_matches_hash_bytes():
    data = b"canonical bytes matter"
    assert sha256_hex(data) == hash_bytes(data).hex()


def test_address_starts_with_KWT():
    kp = generate_keypair()
    addr = address(kp.public)
    assert addr.startswith("KWT")


def test_address_validate_valid_address():
    kp = generate_keypair()
    addr = address(kp.public)
    assert validate_address(addr) is True


def test_address_validate_invalid_prefix_returns_false():
    kp = generate_keypair()
    addr = address(kp.public)
    bad = "XYZ" + addr[3:]
    assert validate_address(bad) is False


def test_address_validate_tampered_address_returns_false():
    kp = generate_keypair()
    addr = address(kp.public)
    # Flip a Base58 character near the end to corrupt checksum.
    mutated = addr[:-1] + ("2" if addr[-1] != "2" else "3")
    assert validate_address(mutated) is False


def test_address_validate_malformed_string_returns_false():
    assert validate_address("not an address") is False
    assert validate_address("") is False


