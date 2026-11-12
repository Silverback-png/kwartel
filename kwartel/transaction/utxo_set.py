"""In-memory UTXO set for Kwartel."""

from __future__ import annotations

from kwartel.transaction.model import Outpoint, Transaction, TxOutput, txid
from kwartel.transaction.validation import validate_tx


class UTXOSet:
    """In-memory set of unspent transaction outputs."""

    def __init__(self) -> None:
        self._data: dict[Outpoint, TxOutput] = {}

    def add_output(self, outpoint: Outpoint, output: TxOutput) -> None:
        """Add an unspent output."""
        self._data[outpoint] = output

    def spend(self, outpoint: Outpoint) -> TxOutput:
        """Remove and return the output for ``outpoint``.

        Raises ``KeyError`` if the outpoint is not unspent.
        """
        return self._data.pop(outpoint)

    def __getitem__(self, outpoint: Outpoint) -> TxOutput:
        """Return the output for ``outpoint``.

        Raises ``KeyError`` if not present.
        """
        return self._data[outpoint]

    def __contains__(self, outpoint: Outpoint) -> bool:
        return outpoint in self._data

    def __len__(self) -> int:
        return len(self._data)

    def balance(self, pubkey: bytes) -> int:
        """Return the total value of outputs locked to ``pubkey``."""
        return sum(output.value for output in self._data.values() if output.lock == pubkey)

    def copy(self) -> "UTXOSet":
        """Return a shallow copy of this UTXO set."""
        new = UTXOSet()
        new._data = dict(self._data)
        return new

    def items(self):
        """Return ``(outpoint, output)`` pairs in this UTXO set."""
        return self._data.items()

    def apply_transaction(self, tx: Transaction) -> None:
        """Validate ``tx`` and update the UTXO set.

        Spends the inputs and adds the outputs keyed by ``(txid(tx), index)``.
        Raises ``ValueError`` if the transaction is invalid.
        """
        violations = validate_tx(tx, self)
        if violations:
            raise ValueError("transaction validation failed:\n" + "\n".join(violations))

        for tx_in in tx.inputs:
            self.spend(tx_in.outpoint)

        tx_id = txid(tx)
        for index, tx_out in enumerate(tx.outputs):
            self.add_output(Outpoint(txid=tx_id, index=index), tx_out)
