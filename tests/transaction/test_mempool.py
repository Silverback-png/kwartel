"""Tests for kwartel.transaction.mempool."""

import pytest

from kwartel.crypto.keys import generate_keypair
from kwartel.transaction.mempool import Mempool
from kwartel.transaction.model import (
    KWARTS_PER_KWT,
    Outpoint,
    Transaction,
    TxInput,
    TxOutput,
)
from kwartel.transaction.utxo_set import UTXOSet


def _fund_and_create_tx(alice, bob, value):
    utxo = UTXOSet()
    fund_outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(fund_outpoint, TxOutput(value=value, lock=alice.public))
    tx = Transaction.create(
        inputs_to_spend={fund_outpoint: TxOutput(value=value, lock=alice.public)},
        recipients=[(value // 2, bob.public)],
        signer=alice,
        change_pubkey=alice.public,
    )
    return utxo, tx, fund_outpoint


def test_accept_valid_tx():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo, tx, _ = _fund_and_create_tx(alice, bob, 100 * KWARTS_PER_KWT)
    mempool = Mempool()
    assert mempool.accept(tx, utxo) is True
    assert len(mempool) == 1


def test_reject_invalid_tx():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo = UTXOSet()
    fund_outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(fund_outpoint, TxOutput(value=10, lock=alice.public))
    tx = Transaction(
        inputs=(TxInput(outpoint=fund_outpoint, unlock_pubkey=alice.public, signature=b"\x00" * 64),),
        outputs=(TxOutput(value=20, lock=bob.public),),
    )
    mempool = Mempool()
    assert mempool.accept(tx, utxo) is False
    assert len(mempool) == 0


def test_reject_double_spend_in_mempool():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo, tx1, fund_outpoint = _fund_and_create_tx(alice, bob, 100 * KWARTS_PER_KWT)
    mempool = Mempool()
    assert mempool.accept(tx1, utxo) is True

    tx2 = Transaction.create(
        inputs_to_spend={fund_outpoint: TxOutput(value=100 * KWARTS_PER_KWT, lock=alice.public)},
        recipients=[(40 * KWARTS_PER_KWT, bob.public)],
        signer=alice,
        change_pubkey=alice.public,
    )
    assert mempool.accept(tx2, utxo) is False
    assert len(mempool) == 1


def test_remove_tx():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo, tx, _ = _fund_and_create_tx(alice, bob, 100 * KWARTS_PER_KWT)
    mempool = Mempool()
    mempool.accept(tx, utxo)
    from kwartel.transaction.model import txid
    tx_id = txid(tx)
    mempool.remove(tx_id)
    assert len(mempool) == 0


def test_get_tx():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo, tx, _ = _fund_and_create_tx(alice, bob, 100 * KWARTS_PER_KWT)
    mempool = Mempool()
    mempool.accept(tx, utxo)
    from kwartel.transaction.model import txid
    tx_id = txid(tx)
    assert mempool.get(tx_id) == tx
    assert mempool.get("missing") is None


def test_all_transactions():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo, tx, _ = _fund_and_create_tx(alice, bob, 100 * KWARTS_PER_KWT)
    mempool = Mempool()
    mempool.accept(tx, utxo)
    assert mempool.all_transactions() == (tx,)


def test_len():
    mempool = Mempool()
    assert len(mempool) == 0
