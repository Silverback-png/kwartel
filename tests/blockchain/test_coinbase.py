"""Tests for kwartel.blockchain.coinbase."""

from kwartel.blockchain.block import Block, BlockHeader
from kwartel.blockchain.coinbase import (
    BLOCK_REWARD,
    COINBASE_MATURITY,
    coinbase_outpoint,
    create_coinbase,
    validate_coinbase,
)
from kwartel.crypto.keys import generate_keypair
from kwartel.transaction.model import KWARTS_PER_KWT, Transaction, TxInput, TxOutput
from kwartel.transaction.validation import is_coinbase


def _header() -> BlockHeader:
    return BlockHeader("00" * 32, "11" * 32, 1757200000, 8, 0)


def _block_with_coinbase(coinbase: Transaction) -> Block:
    return Block(header=_header(), transactions=(coinbase,))


def test_create_coinbase_reward():
    kp = generate_keypair()
    tx = create_coinbase(1, kp.public, 0)
    assert tx.outputs[0].value == BLOCK_REWARD
    assert BLOCK_REWARD == 50 * KWARTS_PER_KWT


def test_create_coinbase_includes_fees():
    kp = generate_keypair()
    tx = create_coinbase(1, kp.public, 1234)
    assert tx.outputs[0].value == BLOCK_REWARD + 1234


def test_create_coinbase_is_coinbase_shape():
    kp = generate_keypair()
    tx = create_coinbase(1, kp.public, 0)
    assert is_coinbase(tx) is True
    assert len(tx.outputs) == 1


def test_coinbase_outpoint_namespaced():
    op = coinbase_outpoint("a" * 64, "b" * 64)
    assert op.txid == "a" * 64 + "b" * 64
    assert op.index == 0


def test_validate_coinbase_valid():
    kp = generate_keypair()
    tx = create_coinbase(1, kp.public, 0)
    block = _block_with_coinbase(tx)
    assert validate_coinbase(tx, block, 0) == []


def test_validate_coinbase_wrong_value():
    kp = generate_keypair()
    tx = create_coinbase(1, kp.public, 0)
    block = _block_with_coinbase(tx)
    violations = validate_coinbase(tx, block, 100)
    assert any("value" in v.lower() for v in violations)


def test_validate_coinbase_has_inputs():
    alice, bob = generate_keypair(), generate_keypair()
    tx_in = TxInput(coinbase_outpoint("a" * 64, "b" * 64), alice.public, b"\x00" * 64)
    tx = Transaction((tx_in,), (TxOutput(BLOCK_REWARD, bob.public),))
    block = _block_with_coinbase(tx)
    assert any("inputs" in v.lower() for v in validate_coinbase(tx, block, 0))


def test_validate_coinbase_multiple_outputs():
    kp = generate_keypair()
    tx = Transaction((), (TxOutput(BLOCK_REWARD, kp.public), TxOutput(1, kp.public)))
    block = _block_with_coinbase(tx)
    assert any("exactly one output" in v.lower() for v in validate_coinbase(tx, block, 0))


def test_validate_coinbase_not_first():
    kp = generate_keypair()
    coinbase = create_coinbase(1, kp.public, 0)
    other = create_coinbase(1, kp.public, 0)
    # coinbase not in position 0
    block = Block(header=_header(), transactions=(other, coinbase))
    assert any("first transaction" in v.lower() for v in validate_coinbase(coinbase, block, 0))


def test_maturity_constant():
    assert COINBASE_MATURITY == 1
