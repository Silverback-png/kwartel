"""Coinbase construction and validation for Kwartel."""

from __future__ import annotations

from kwartel.blockchain.block import Block
from kwartel.transaction.model import KWARTS_PER_KWT, Outpoint, Transaction, TxOutput
from kwartel.transaction.validation import is_coinbase

BLOCK_REWARD = 50 * KWARTS_PER_KWT
COINBASE_MATURITY = 1


def create_coinbase(block_height: int, payout_pubkey: bytes, fee_total: int) -> Transaction:
    """Return the coinbase transaction for a block at ``block_height``.

    The coinbase has no inputs and exactly one output worth
    ``BLOCK_REWARD + fee_total`` locked to ``payout_pubkey``.  ``block_height``
    is accepted for API clarity but is intentionally not encoded into the txid:
    coinbase outpoints are namespaced by their block hash instead (see
    ``coinbase_outpoint``), which keeps Task 02 dataclasses untouched.
    """
    return Transaction(
        inputs=(),
        outputs=(TxOutput(value=BLOCK_REWARD + fee_total, lock=payout_pubkey),),
    )


def coinbase_outpoint(block_hash: str, coinbase_txid: str) -> Outpoint:
    """Return the UTXO outpoint for a coinbase output.

    Coinbase txids can collide across blocks (same reward, same payout pubkey,
    zero fees).  Prefixing the txid with the unique ``block_hash`` guarantees a
    unique, spendable outpoint for every coinbase output without modifying the
    Task 02 dataclasses.
    """
    return Outpoint(txid=block_hash + coinbase_txid, index=0)


def validate_coinbase(tx: Transaction, block: Block, actual_fees: int) -> list[str]:
    """Return a list of violations for a coinbase transaction (never raises).

    Checks: no inputs, exactly one output, value == ``BLOCK_REWARD + actual_fees``,
    and that the coinbase is the block's first transaction and the block's only
    coinbase.
    """
    try:
        violations: list[str] = []

        if not is_coinbase(tx):
            violations.append("coinbase transaction has inputs")

        if len(tx.outputs) != 1:
            violations.append("coinbase transaction must have exactly one output")
            return violations

        expected = BLOCK_REWARD + actual_fees
        if tx.outputs[0].value != expected:
            violations.append(
                f"coinbase value {tx.outputs[0].value} != expected {expected}"
            )

        if not block.transactions or block.transactions[0] is not tx:
            violations.append("coinbase must be the first transaction in the block")

        coinbase_count = sum(1 for t in block.transactions if is_coinbase(t))
        if coinbase_count != 1:
            violations.append("block must contain exactly one coinbase transaction")

        return violations
    except Exception as exc:  # pragma: no cover - defensive guard
        return [f"validate_coinbase raised exception: {exc}"]
