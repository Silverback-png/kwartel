"""Block and header model for Kwartel.

A block bundles a header and a list of transactions.  The header commits to
the previous block hash and the Merkle root of the transactions, so any change
to history or to the transaction set changes every subsequent header hash.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, replace

from kwartel.crypto.keys import hash_bytes, sha256_hex
from kwartel.transaction.model import Transaction
from kwartel.transaction.validation import is_coinbase

_U32 = struct.Struct("<I")
_U64 = struct.Struct("<Q")


@dataclass(frozen=True)
class BlockHeader:
    """Consensus-critical block header."""

    prev_block_hash: str  # 64 hex chars (32 bytes)
    merkle_root: str      # 64 hex chars (32 bytes)
    timestamp: int        # unix seconds, non-negative
    difficulty: int       # leading zero bits required on header hash
    nonce: int            # u64


@dataclass(frozen=True)
class Block:
    """A block: header plus the transactions it commits to."""

    header: BlockHeader
    transactions: tuple[Transaction, ...]


def _encode_bytes(data: bytes) -> bytes:
    """Length-prefixed byte string: u32 LE length + raw bytes."""
    return _U32.pack(len(data)) + data


def serialize_header(h: BlockHeader) -> bytes:
    """Return a canonical, length-prefixed serialization of ``h``.

    Layout: prev_block_hash(32 raw, len-prefixed), merkle_root(32 raw,
    len-prefixed), timestamp(u64 LE), difficulty(u32 LE), nonce(u64 LE).
    """
    data = b""
    data += _encode_bytes(bytes.fromhex(h.prev_block_hash))
    data += _encode_bytes(bytes.fromhex(h.merkle_root))
    data += _U64.pack(h.timestamp)
    data += _U32.pack(h.difficulty)
    data += _U64.pack(h.nonce)
    return data


def block_hash(header: BlockHeader) -> str:
    """Return the hex SHA-256 block hash of ``header``."""
    return sha256_hex(serialize_header(header))

def leading_zero_bits(hex_hash: str) -> int:
    """Count the number of leading zero bits in ``hex_hash``.

    Each hex character represents 4 bits.  For the first non-zero nibble, only the
    actually-leading zero bits are counted.  The result is deterministic and
    works for any valid hex hash.
    """
    count = 0
    for char in hex_hash:
        if char == "0":
            count += 4
            continue
        nibble = int(char, 16)
        bits = 0
        while nibble < 8:
            bits += 1
            nibble <<= 1
        count += bits
        break
    return count


def meets_difficulty(header: BlockHeader) -> bool:
    """Return True if ``header`` hash satisfies ``header.difficulty``."""
    return leading_zero_bits(block_hash(header)) >= header.difficulty


def mine_block(header_template: BlockHeader, max_nonce: int = 2**64) -> BlockHeader:
    """Increment nonce from 0 until ``meets_difficulty`` is satisfied.

    Deterministic: the same ``header_template`` always yields the same mined
    header because the nonce search starts at 0 and scans upward.  Raises
    ``RuntimeError`` if ``max_nonce`` is exhausted.
    """
    for nonce in range(max_nonce):
        candidate = replace(header_template, nonce=nonce)
        if meets_difficulty(candidate):
            return candidate
    raise RuntimeError("no nonce satisfies difficulty within max_nonce")


def is_coinbase_only(block: Block) -> bool:
    """Return True if ``block`` consists of exactly one coinbase transaction."""
    return len(block.transactions) == 1 and is_coinbase(block.transactions[0])


def _light_tx_structure_violations(tx: Transaction) -> list[str]:
    """Return structural violations for a single transaction (no UTXO lookup)."""
    violations: list[str] = []
    if not tx.outputs:
        violations.append("transaction has no outputs")
    for idx, tx_out in enumerate(tx.outputs):
        if tx_out.value < 1:
            violations.append(f"output {idx} value {tx_out.value} is below minimum 1")
        if len(tx_out.lock) != 32:
            violations.append(f"output {idx} lock length is {len(tx_out.lock)}, expected 32")
    return violations


def validate_block_structure(block: Block) -> list[str]:
    """Return all structural violations for ``block``.

    This performs only light structural checks that do not require a UTXO set
    or full transaction validation (those come in Task 04).  It never raises.
    """
    try:
        violations: list[str] = []
        h = block.header

        def _check_hex(field: str, value: str, expected_len: int) -> None:
            if not isinstance(value, str):
                violations.append(f"{field} must be a hex string")
                return
            if len(value) != expected_len:
                violations.append(f"{field} length is {len(value)}, expected {expected_len}")
            try:
                bytes.fromhex(value)
            except ValueError:
                violations.append(f"{field} is not valid hex")

        _check_hex("prev_block_hash", h.prev_block_hash, 64)
        _check_hex("merkle_root", h.merkle_root, 64)

        if not isinstance(h.timestamp, int) or isinstance(h.timestamp, bool):
            violations.append("timestamp must be a non-negative integer")
        elif h.timestamp < 0:
            violations.append("timestamp must be non-negative")

        if not isinstance(h.difficulty, int) or isinstance(h.difficulty, bool):
            violations.append("difficulty must be a positive integer")
        elif h.difficulty < 1:
            violations.append("difficulty must be at least 1")

        if not isinstance(h.nonce, int) or isinstance(h.nonce, bool):
            violations.append("nonce must be an integer in [0, 2^64)")
        elif h.nonce < 0 or h.nonce >= 2**64:
            violations.append("nonce is outside u64 range")

        if not block.transactions:
            violations.append("block has no transactions")

        coinbase_count = 0
        for idx, tx in enumerate(block.transactions):
            if not isinstance(tx, Transaction):
                violations.append(f"transaction {idx} is not a Transaction instance")
                continue
            if is_coinbase(tx):
                coinbase_count += 1
            for v in _light_tx_structure_violations(tx):
                violations.append(f"transaction {idx}: {v}")

        if coinbase_count > 1:
            violations.append("block contains more than one coinbase transaction")

        return violations
    except Exception as exc:  # pragma: no cover - defensive guard
        return [f"validate_block_structure raised exception: {exc}"]

