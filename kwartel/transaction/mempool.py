"""Mempool of pending, valid transactions for Kwartel."""

from __future__ import annotations

from kwartel.transaction.model import Transaction, txid
from kwartel.transaction.validation import validate_tx
from kwartel.transaction.utxo_set import UTXOSet


class Mempool:
    """In-memory pool of valid-but-unmined transactions."""

    def __init__(self) -> None:
        self._txs: dict[str, Transaction] = {}

    def accept(self, tx: Transaction, utxo_set: UTXOSet) -> bool:
        """Validate ``tx`` and add it to the mempool if valid and non-conflicting.

        Also rejects the transaction if any of its inputs are already consumed by
        another transaction in the mempool.
        """
        # Mempool-level double-spend check.
        for tx_in in tx.inputs:
            for existing in self._txs.values():
                for existing_in in existing.inputs:
                    if existing_in.outpoint == tx_in.outpoint:
                        return False

        violations = validate_tx(tx, utxo_set)
        if violations:
            return False

        self._txs[txid(tx)] = tx
        return True

    def remove(self, txid_str: str) -> None:
        """Remove the transaction with the given txid from the mempool."""
        self._txs.pop(txid_str, None)

    def get(self, txid_str: str) -> Transaction | None:
        """Return the transaction with the given txid, or None."""
        return self._txs.get(txid_str)

    def all_transactions(self) -> tuple[Transaction, ...]:
        """Return all transactions currently in the mempool."""
        return tuple(self._txs.values())

    def __len__(self) -> int:
        return len(self._txs)
