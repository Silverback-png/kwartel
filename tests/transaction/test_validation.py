"""Tests for kwartel.transaction.validation."""

import pytest

from kwartel.crypto.keys import generate_keypair, hash_bytes, sign
from kwartel.transaction.model import (
    KWARTS_PER_KWT,
    Outpoint,
    Transaction,
    TxInput,
    TxOutput,
    serialize_tx,
)
from kwartel.transaction.utxo_set import UTXOSet
from kwartel.transaction.validation import is_coinbase, validate_tx


def _make_signed_tx(outpoint, outputs, signer):
    unsigned_input = TxInput(
        outpoint=outpoint,
        unlock_pubkey=signer.public,
        signature=b"",
    )
    unsigned_tx = Transaction(inputs=(unsigned_input,), outputs=tuple(outputs))
    txid_bytes = hash_bytes(serialize_tx(unsigned_tx, include_signatures=False))
    sig = sign(signer.secret, txid_bytes)
    signed_input = TxInput(
        outpoint=outpoint,
        unlock_pubkey=signer.public,
        signature=sig,
    )
    return Transaction(inputs=(signed_input,), outputs=tuple(outputs))


def test_empty_inputs_rejected():
    alice = generate_keypair()
    utxo = UTXOSet()
    tx = Transaction(inputs=(), outputs=(TxOutput(value=10, lock=alice.public),))
    violations = validate_tx(tx, utxo)
    assert any("input" in v.lower() for v in violations)


def test_empty_outputs_rejected():
    alice = generate_keypair()
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(outpoint, TxOutput(value=10, lock=alice.public))
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=alice.public, signature=b"\x00" * 64)
    tx = Transaction(inputs=(tx_in,), outputs=())
    violations = validate_tx(tx, utxo)
    assert any("output" in v.lower() for v in violations)


def test_unknown_outpoint_rejected():
    alice = generate_keypair()
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=alice.public, signature=b"\x00" * 64)
    tx = Transaction(inputs=(tx_in,), outputs=(TxOutput(value=10, lock=alice.public),))
    violations = validate_tx(tx, utxo)
    assert any("not found" in v.lower() or "unknown" in v.lower() for v in violations)


def test_duplicate_outpoint_rejected():
    alice = generate_keypair()
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(outpoint, TxOutput(value=20, lock=alice.public))
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=alice.public, signature=b"\x00" * 64)
    tx = Transaction(inputs=(tx_in, tx_in), outputs=(TxOutput(value=20, lock=alice.public),))
    violations = validate_tx(tx, utxo)
    assert any("duplicate" in v.lower() for v in violations)


def test_wrong_unlock_pubkey_rejected():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(outpoint, TxOutput(value=10, lock=alice.public))
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=bob.public, signature=b"\x00" * 64)
    tx = Transaction(inputs=(tx_in,), outputs=(TxOutput(value=10, lock=bob.public),))
    violations = validate_tx(tx, utxo)
    assert any("pubkey" in v.lower() or "owner" in v.lower() for v in violations)


def test_invalid_signature_rejected():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(outpoint, TxOutput(value=10, lock=alice.public))
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=alice.public, signature=b"\xff" * 64)
    tx = Transaction(inputs=(tx_in,), outputs=(TxOutput(value=10, lock=bob.public),))
    violations = validate_tx(tx, utxo)
    assert any("signature" in v.lower() for v in violations)


def test_outputs_exceed_inputs_rejected():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(outpoint, TxOutput(value=10, lock=alice.public))
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=alice.public, signature=b"\x00" * 64)
    tx = Transaction(inputs=(tx_in,), outputs=(TxOutput(value=20, lock=bob.public),))
    violations = validate_tx(tx, utxo)
    assert any("exceed" in v.lower() or "conservation" in v.lower() for v in violations)
def test_negative_output_rejected():
    alice = generate_keypair()
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(outpoint, TxOutput(value=10, lock=alice.public))
    neg_output = TxOutput(value=0, lock=alice.public)
    object.__setattr__(neg_output, "value", -1)
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=alice.public, signature=b"\x00" * 64)
    tx = Transaction(inputs=(tx_in,), outputs=(neg_output,))
    violations = validate_tx(tx, utxo)
    assert any("negative" in v.lower() for v in violations)


def test_zero_output_rejected():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(outpoint, TxOutput(value=10, lock=alice.public))
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=alice.public, signature=b"\x00" * 64)
    tx = Transaction(inputs=(tx_in,), outputs=(TxOutput(value=0, lock=bob.public),))
    violations = validate_tx(tx, utxo)
    assert any("dust" in v.lower() or "zero" in v.lower() for v in violations)


def test_coinbase_rejected_when_not_allowed():
    alice = generate_keypair()
    utxo = UTXOSet()
    tx = Transaction(inputs=(), outputs=(TxOutput(value=50 * KWARTS_PER_KWT, lock=alice.public),))
    violations = validate_tx(tx, utxo, allow_coinbase=False)
    assert any("coinbase" in v.lower() for v in violations)


def test_valid_tx_returns_no_violations():
    alice = generate_keypair()
    bob = generate_keypair()
    utxo = UTXOSet()
    outpoint = Outpoint(txid="a" * 64, index=0)
    utxo.add_output(outpoint, TxOutput(value=100 * KWARTS_PER_KWT, lock=alice.public))
    tx = _make_signed_tx(
        outpoint,
        [
            TxOutput(value=50 * KWARTS_PER_KWT, lock=bob.public),
            TxOutput(value=50 * KWARTS_PER_KWT, lock=alice.public),
        ],
        alice,
    )
    violations = validate_tx(tx, utxo)
    assert violations == []


def test_is_coinbase_true_for_empty_inputs():
    alice = generate_keypair()
    tx = Transaction(inputs=(), outputs=(TxOutput(value=50 * KWARTS_PER_KWT, lock=alice.public),))
    assert is_coinbase(tx) is True


def test_is_coinbase_false_for_inputs():
    alice = generate_keypair()
    outpoint = Outpoint(txid="a" * 64, index=0)
    tx_in = TxInput(outpoint=outpoint, unlock_pubkey=alice.public, signature=b"\x00" * 64)
    tx = Transaction(inputs=(tx_in,), outputs=())
    assert is_coinbase(tx) is False

