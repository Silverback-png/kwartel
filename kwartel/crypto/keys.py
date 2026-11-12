"""Ed25519 keypair generation, signing, and verification for Kwartel."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from nacl.bindings import crypto_sign, crypto_sign_open, crypto_sign_seed_keypair

from kwartel.crypto.base58 import b58check_decode, b58check_encode


@dataclass(frozen=True)
class KeyPair:
    """A 32-byte Ed25519 seed and its derived 32-byte public key."""

    secret: bytes
    public: bytes


def generate_keypair() -> KeyPair:
    """Generate a random Ed25519 keypair.

    The 32-byte seed is stored as ``secret``; it can be backed up directly as
    the wallet secret. The public key is deterministically derived from it.
    """
    seed = os.urandom(32)
    public_key = derive_public(seed)
    return KeyPair(secret=seed, public=public_key)


def derive_public(secret: bytes) -> bytes:
    """Derive the 32-byte Ed25519 public key from a 32-byte seed."""
    public_key, _signing_key = crypto_sign_seed_keypair(secret)
    return public_key


def _signing_key(seed: bytes) -> bytes:
    """Return the 64-byte Ed25519 signing key (seed || public) for a seed."""
    _public_key, signing_key = crypto_sign_seed_keypair(seed)
    return signing_key


def sign(secret: bytes, message: bytes) -> bytes:
    """Sign ``message`` with the 32-byte Ed25519 seed ``secret``.

    Returns the 64-byte detached Ed25519 signature.
    """
    signing_key = _signing_key(secret)
    signed_message = crypto_sign(message, signing_key)
    return signed_message[:64]


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """Verify a detached Ed25519 ``signature`` on ``message`` using ``public``.

    Returns ``False`` for any malformed input, wrong key, tampered message, or
    tampered signature. Never raises.
    """
    try:
        if len(signature) != 64 or len(public) != 32:
            return False
        signed_message = signature + message
        crypto_sign_open(signed_message, public)
        return True
    except Exception:
        return False


def hash_bytes(data: bytes) -> bytes:
    """Return the raw 32-byte SHA-256 digest of ``data``."""
    return hashlib.sha256(data).digest()


def sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


ADDRESS_PREFIX = "KWT"
ADDRESS_VERSION = b"\x00"


def address(public: bytes) -> str:
    """Return the Kwartel address for a 32-byte Ed25519 public key."""
    payload = ADDRESS_VERSION + public
    return ADDRESS_PREFIX + b58check_encode(payload)


def validate_address(addr: str) -> bool:
    """Check that ``addr`` is a well-formed Kwartel address.

    Validates the prefix, version byte, and Base58Check checksum. Never raises.
    """
    try:
        if not isinstance(addr, str) or not addr.startswith(ADDRESS_PREFIX):
            return False
        encoded = addr[len(ADDRESS_PREFIX) :]
        payload = b58check_decode(encoded)
        if len(payload) != 33:
            return False
        return payload[0:1] == ADDRESS_VERSION
    except Exception:
        return False

