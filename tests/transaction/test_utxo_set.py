"""Tests for kwartel.transaction.utxo_set."""

import pytest

from kwartel.crypto.keys import generate_keypair
from kwartel.transaction.model import (
    KWARTS_PER_KWT,
    Outpoint,
    Transaction,
    TxInput,
    TxOutput,
)
from kwartel.transaction.utxo_set import UTXOSet


def test_add_output_and_contains():
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    output = TxOutput(value=10, lock=b"x" * 32)
    utxo.add_output(outpoint, output)
    assert outpoint in utxo
    assert utxo[outpoint] == output


def test_spend_removes_output():
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    output = TxOutput(value=10, lock=b"x" * 32)
    utxo.add_output(outpoint, output)
    spent = utxo.spend(outpoint)
    assert spent == output
    assert outpoint not in utxo


def test_spend_missing_raises_keyerror():
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    with pytest.raises(KeyError):
        utxo.spend(outpoint)


def test_len():
    utxo = UTXOSet()
    assert len(utxo) == 0
    utxo.add_output(Outpoint(txid="a" * 64, index=0), TxOutput(value=10, lock=b"x" * 32))
    assert len(utxo) == 1


def test_balance_sums_correctly():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo = UTXOSet()
    utxo.add_output(Outpoint(txid="a" * 64, index=0), TxOutput(value=30, lock=alice.public))
    utxo.add_output(Outpoint(txid="a" * 64, index=1), TxOutput(value=70, lock=alice.public))
    utxo.add_output(Outpoint(txid="b" * 64, index=0), TxOutput(value=50, lock=bob.public))
    assert utxo.balance(alice.public) == 100
    assert utxo.balance(bob.public) == 50


def test_apply_transaction_spends_and_creates():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo = UTXOSet()
    fund_outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(fund_outpoint, TxOutput(value=100 * KWARTS_PER_KWT, lock=alice.public))

    tx = Transaction.create(
        inputs_to_spend={fund_outpoint: TxOutput(value=100 * KWARTS_PER_KWT, lock=alice.public)},
        recipients=[(50 * KWARTS_PER_KWT, bob.public)],
        signer=alice,
        change_pubkey=alice.public,
    )
    utxo.apply_transaction(tx)

    assert fund_outpoint not in utxo
    assert utxo.balance(alice.public) == 50 * KWARTS_PER_KWT
    assert utxo.balance(bob.public) == 50 * KWARTS_PER_KWT


def test_apply_invalid_tx_raises_valueerror():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo = UTXOSet()
    fund_outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(fund_outpoint, TxOutput(value=10, lock=alice.public))
    tx = Transaction(
        inputs=(TxInput(outpoint=fund_outpoint, unlock_pubkey=alice.public, signature=b"\x00" * 64),),
        outputs=(TxOutput(value=20, lock=bob.public),),
    )
    with pytest.raises(ValueError):
        utxo.apply_transaction(tx)


def test_double_spend_within_tx_rejected():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo = UTXOSet()
    fund_outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(fund_outpoint, TxOutput(value=100, lock=alice.public))
    tx_in = TxInput(outpoint=fund_outpoint, unlock_pubkey=alice.public, signature=b"\x00" * 64)
    tx = Transaction(
        inputs=(tx_in, tx_in),
        outputs=(TxOutput(value=100, lock=bob.public),),
    )
    with pytest.raises(ValueError):
        utxo.apply_transaction(tx)


def test_double_spend_across_txs_rejected():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo = UTXOSet()
    fund_outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(fund_outpoint, TxOutput(value=100 * KWARTS_PER_KWT, lock=alice.public))

    tx1 = Transaction.create(
        inputs_to_spend={fund_outpoint: TxOutput(value=100 * KWARTS_PER_KWT, lock=alice.public)},
        recipients=[(50 * KWARTS_PER_KWT, bob.public)],
        signer=alice,
        change_pubkey=alice.public,
    )
    utxo.apply_transaction(tx1)

    tx2 = Transaction.create(
        inputs_to_spend={fund_outpoint: TxOutput(value=50 * KWARTS_PER_KWT, lock=alice.public)},
        recipients=[(50 * KWARTS_PER_KWT, bob.public)],
        signer=alice,
        change_pubkey=alice.public,
    )
    with pytest.raises(ValueError):
        utxo.apply_transaction(tx2)
