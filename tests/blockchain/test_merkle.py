"""Tests for kwartel.blockchain.merkle."""

import hashlib

from kwartel.blockchain.merkle import merkle_root
from kwartel.crypto.keys import sha256_hex


def _pair(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(left + right).digest()


def _manual_root(txids_hex: list[str]) -> str:
    level = [bytes.fromhex(t) for t in txids_hex]
    while True:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        if len(level) == 1:
            break
    return level[0].hex()


def test_empty_list_returns_sha256_of_empty():
    assert merkle_root([]) == sha256_hex(b"")


def test_single_tx_duplicates_itself():
    leaf = bytes.fromhex("a" * 64)
    expected = hashlib.sha256(leaf + leaf).hexdigest()
    assert merkle_root(["a" * 64]) == expected


def test_known_4_leaf_vector():
    leaves = ["aa" * 32, "bb" * 32, "cc" * 32, "dd" * 32]
    expected = _manual_root(leaves)
    assert merkle_root(leaves) == expected


def test_odd_count_duplicates_last():
    leaves = ["aa" * 32, "bb" * 32, "cc" * 32]
    expected = _manual_root(leaves)
    assert merkle_root(leaves) == expected


def test_odd_count_at_multiple_levels():
    leaves = ["aa" * 32, "bb" * 32, "cc" * 32, "dd" * 32, "ee" * 32]
    expected = _manual_root(leaves)
    assert merkle_root(leaves) == expected


def test_order_sensitivity():
    leaves = ["aa" * 32, "bb" * 32, "cc" * 32, "dd" * 32]
    root1 = merkle_root(leaves)
    root2 = merkle_root([leaves[1], leaves[0], leaves[2], leaves[3]])
    assert root1 != root2


def test_determinism():
    leaves = ["aa" * 32, "bb" * 32, "cc" * 32, "dd" * 32]
    assert merkle_root(leaves) == merkle_root(leaves)


def test_duplicate_leaves_produce_same_root():
    """Document CVE-2012-2459: identical leaves may yield the same root.

    With odd-node duplication, two duplicate leaves can sometimes be rearranged
    without changing the root.  This is a structural weakness of naive Merkle
    trees; Kwartel mitigates it by validating the actual transactions inside the
    block, not by trusting the root alone.
    """
    leaves = ["aa" * 32, "bb" * 32, "cc" * 32]
    root1 = merkle_root(leaves)
    root2 = merkle_root(["aa" * 32, "bb" * 32, "cc" * 32, "cc" * 32])
    assert root1 == root2
