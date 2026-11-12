"""Transaction validation rules for Kwartel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kwartel.crypto.keys import hash_bytes, verify
from kwartel.transaction.model import Outpoint, Transaction, TxInput, TxOutput, serialize_tx

if TYPE_CHECKING:
    from kwartel.transaction.utxo_set import UTXOSet


def is_coinbase(tx: Transaction) -> bool:
    """Return True if ``tx`` has no inputs (coinbase shape)."""
    return len(tx.inputs) == 0


def validate_tx(
    tx: Transaction,
    utxo_set: UTXOSet,
    *,
    allow_coinbase: bool = False,
) -> list[str]:
    """Return a list of all validation violations for ``tx``.

    An empty list means the transaction is valid. Never raises.
    """
    try:
        violations: list[str] = []

        # 1. Non-empty inputs and outputs.
        if not tx.inputs:
            violations.append("transaction has no inputs")
        if not tx.outputs:
            violations.append("transaction has no outputs")

        # 9. Coinbase rejection unless explicitly allowed.
        if is_coinbase(tx) and not allow_coinbase:
            violations.append("coinbase transactions are not allowed here")

        # Early value checks (serialization fails on negatives).
        for tx_out in tx.outputs:
            if tx_out.value < 0:
                violations.append("output value is negative")
            if tx_out.value == 0:
                violations.append("dust output (value must be > 0)")

        # If there are no inputs, the remaining checks do not apply.
        if not tx.inputs:
            return violations

        # 3. No duplicate outpoints within the tx.
        seen_outpoints: set[Outpoint] = set()
        for tx_in in tx.inputs:
            if tx_in.outpoint in seen_outpoints:
                violations.append(f"duplicate outpoint: {tx_in.outpoint}")
            seen_outpoints.add(tx_in.outpoint)

        # 2, 4, 5. Existence, owner match, and signature.
        txid_bytes = hash_bytes(serialize_tx(tx, include_signatures=False))
        for tx_in in tx.inputs:
            if tx_in.outpoint not in utxo_set:
                violations.append(f"outpoint not found: {tx_in.outpoint}")
                continue

            utxo_output = utxo_set[tx_in.outpoint]
            if tx_in.unlock_pubkey != utxo_output.lock:
                violations.append(
                    f"input {tx_in.outpoint} unlock pubkey does not match output lock"
                )
                continue

            if not verify(tx_in.unlock_pubkey, txid_bytes, tx_in.signature):
                violations.append(f"input {tx_in.outpoint} has invalid signature")

        # 6, 8. Conservation.
        total_in = 0
        counted: set[Outpoint] = set()
        for tx_in in tx.inputs:
            if tx_in.outpoint in utxo_set and tx_in.outpoint not in counted:
                total_in += utxo_set[tx_in.outpoint].value
                counted.add(tx_in.outpoint)

        total_out = sum(tx_out.value for tx_out in tx.outputs)
        if total_out > total_in:
            violations.append("outputs exceed inputs (conservation violation)")

        return violations
    except Exception as exc:
        return [f"validation raised exception: {exc}"]

