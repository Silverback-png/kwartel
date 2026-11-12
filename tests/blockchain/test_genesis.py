"""Tests for kwartel.blockchain.genesis."""

from kwartel.blockchain.block import block_hash
from kwartel.blockchain.genesis import (
    GENESIS_HASH,
    GENESIS_NONCE,
    GENESIS_PAYOUT,
    create_genesis_block,
)
from kwartel.transaction.validation import is_coinbase
from kwartel.blockchain.block import validate_block_structure


def test_genesis_is_deterministic():
    g1 = create_genesis_block(GENESIS_PAYOUT)
    g2 = create_genesis_block(GENESIS_PAYOUT)
    assert g1 == g2
    assert block_hash(g1.header) == block_hash(g2.header)


def test_genesis_hash_matches_hardcoded_value():
    genesis = create_genesis_block(GENESIS_PAYOUT)
    assert genesis.header.nonce == GENESIS_NONCE
    assert block_hash(genesis.header) == GENESIS_HASH


def test_genesis_passes_structure_validation():
    genesis = create_genesis_block(GENESIS_PAYOUT)
    assert validate_block_structure(genesis) == []


def test_genesis_is_coinbase_only():
    genesis = create_genesis_block(GENESIS_PAYOUT)
    assert len(genesis.transactions) == 1
    assert is_coinbase(genesis.transactions[0]) is True
