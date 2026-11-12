"""Merkle tree hashing for Kwartel blocks.

Merkle trees let a block header commit to an arbitrary number of transactions
with only a 32-byte root.  A light client that knows the root can verify that a
transaction is included in the block by receiving O(log n) sibling hashes.
"""

from __future__ import annotations

from kwartel.crypto.keys import hash_bytes, sha256_hex


def merkle_root(txids_hex: list[str]) -> str:
    """Return the hex SHA-256 Merkle root of ``txids_hex``.

    Each txid is treated as a raw 32-byte digest.  Internal nodes are
    ``sha256(left || right)`` (single SHA-256).  If a level has an odd number of
    nodes, the LAST node is duplicated (Bitcoin-style).  This rule is applied
    uniformly, so a single leaf is duplicated and hashed once, producing a
    different value than the raw leaf.

    An empty list yields ``sha256(b"")`` so the function is total.
    """
    if not txids_hex:
        return sha256_hex(b"")

    level = [bytes.fromhex(txid) for txid in txids_hex]
    while True:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level = [hash_bytes(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
        level = next_level
        if len(level) == 1:
            break
    return level[0].hex()
