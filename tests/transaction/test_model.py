"""Tests for kwartel.transaction.model."""

import pytest

from kwartel.crypto.keys import generate_keypair, hash_bytes
from kwartel.transaction.model import (
    KWARTS_PER_KWT,
    Outpoint,
    Transaction,
    TxInput,
    TxOutput,
    serialize_tx,
    txid,
)


def test_outpoint_is_frozen():
    o = Outpoint(txid="a" * 64, index=0)
    with pytest.raises(AttributeError):
        o.index = 1


def test_txoutput_rejects_negative_value():
    with pytest.raises(ValueError):
        TxOutput(value=-1, lock=b"x" * 32)


def test_txoutput_allows_zero_value():
    # Zero is allowed at construction; validation rejects it as dust.
    TxOutput(value=0, lock=b"x" * 32)


def test_serialize_tx_is_stable():
    kp = generate_keypair()
    outpoint = Outpoint(txid="a" * 64, index=0)
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=kp.public, signature=b"\x00" * 64)
    tx_out = TxOutput(value=100, lock=kp.public)
    tx = Transaction(inputs=(tx_in,), outputs=(tx_out,))
    s1 = serialize_tx(tx, include_signatures=True)
    s2 = serialize_tx(tx, include_signatures=True)
    assert s1 == s2


def test_serialize_tx_signature_independent():
    kp = generate_keypair()
    outpoint = Outpoint(txid="a" * 64, index=0)
    tx_in_1 = TxInput(outpoint=outpoint, unlock_pubkey=kp.public, signature=b"\x00" * 64)
    tx_in_2 = TxInput(outpoint=outpoint, unlock_pubkey=kp.public, signature=b"\xff" * 64)
    tx_out = TxOutput(value=100, lock=kp.public)
    tx1 = Transaction(inputs=(tx_in_1,), outputs=(tx_out,))
    tx2 = Transaction(inputs=(tx_in_2,), outputs=(tx_out,))
    assert serialize_tx(tx1, include_signatures=False) == serialize_tx(tx2, include_signatures=False)


def test_txid_is_64_hex_chars():
    kp = generate_keypair()
    outpoint = Outpoint(txid="a" * 64, index=0)
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=kp.public, signature=b"\x00" * 64)
    tx_out = TxOutput(value=100, lock=kp.public)
    tx = Transaction(inputs=(tx_in,), outputs=(tx_out,))
    assert len(txid(tx)) == 64


def test_txid_ignores_signature_changes():
    kp = generate_keypair()
    outpoint = Outpoint(txid="a" * 64, index=0)
    tx_in_1 = TxInput(outpoint=outpoint, unlock_pubkey=kp.public, signature=b"\x00" * 64)
    tx_in_2 = TxInput(outpoint=outpoint, unlock_pubkey=kp.public, signature=b"\xff" * 64)
    tx_out = TxOutput(value=100, lock=kp.public)
    tx1 = Transaction(inputs=(tx_in_1,), outputs=(tx_out,))
    tx2 = Transaction(inputs=(tx_in_2,), outputs=(tx_out,))
    assert txid(tx1) == txid(tx2)


def test_txid_changes_with_output_changes():
    kp = generate_keypair()
    outpoint = Outpoint(txid="a" * 64, index=0)
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=kp.public, signature=b"\x00" * 64)
    tx_out_1 = TxOutput(value=100, lock=kp.public)
    tx_out_2 = TxOutput(value=200, lock=kp.public)
    tx1 = Transaction(inputs=(tx_in,), outputs=(tx_out_1,))
    tx2 = Transaction(inputs=(tx_in,), outputs=(tx_out_2,))
    assert txid(tx1) != txid(tx2)


def test_transaction_create_signs_inputs():
    alice = generate_keypair()
    bob = generate_keypair()
    outpoint = Outpoint(txid="a" * 64, index=0)
    available = {outpoint: TxOutput(value=100 * KWARTS_PER_KWT, lock=alice.public)}
    tx = Transaction.create(
        inputs_to_spend=available,
        recipients=[(50 * KWARTS_PER_KWT, bob.public)],
        signer=alice,
        change_pubkey=alice.public,
    )
    assert len(tx.inputs) == 1
    assert len(tx.outputs) == 2  # payment + change
    assert tx.inputs[0].signature != b"\x00" * 64
    assert len(tx.inputs[0].signature) == 64


def test_transaction_create_computes_change():
    alice = generate_keypair()
    bob = generate_keypair()
    outpoint = Outpoint(txid="a" * 64, index=0)
    available = {outpoint: TxOutput(value=100 * KWARTS_PER_KWT, lock=alice.public)}
    tx = Transaction.create(
        inputs_to_spend=available,
        recipients=[(50 * KWARTS_PER_KWT, bob.public)],
        signer=alice,
        change_pubkey=alice.public,
    )
    values = [out.value for out in tx.outputs]
    assert 50 * KWARTS_PER_KWT in values
    assert 50 * KWARTS_PER_KWT in values  # change


def test_transaction_create_insufficient_funds():
    alice = generate_keypair()
    bob = generate_keypair()
    outpoint = Outpoint(txid="a" * 64, index=0)
    available = {outpoint: TxOutput(value=10 * KWARTS_PER_KWT, lock=alice.public)}
    with pytest.raises(ValueError):
        Transaction.create(
            inputs_to_spend=available,
            recipients=[(50 * KWARTS_PER_KWT, bob.public)],
            signer=alice,
            change_pubkey=alice.public,
        )


def test_kwarts_per_kwt_constant():
    assert KWARTS_PER_KWT == 100_000_000
