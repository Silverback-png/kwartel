"""Demo script for kwartel.transaction."""

from __future__ import annotations

from kwartel.crypto.keys import address, generate_keypair
from kwartel.transaction.model import (
    KWARTS_PER_KWT,
    Outpoint,
    Transaction,
    TxOutput,
    txid,
)
from kwartel.transaction.validation import validate_tx
from kwartel.transaction.utxo_set import UTXOSet


def _kwt_str(kwarts: int) -> str:
    """Return a human-readable KWT string without using float."""
    return f"{kwarts // KWARTS_PER_KWT} KWT ({kwarts} kwarts)"


def main() -> None:
    alice = generate_keypair()
    bob = generate_keypair()

    print(f"Alice address: {address(alice.public)}")
    print(f"Bob address:   {address(bob.public)}")
    print()

    # Manually seed Alice with a genesis-style UTXO.
    utxo = UTXOSet()
    genesis_outpoint = Outpoint(txid="0" * 64, index=0)
    genesis_output = TxOutput(value=100 * KWARTS_PER_KWT, lock=alice.public)
    utxo.add_output(genesis_outpoint, genesis_output)
    print(f"Initial UTXO set size: {len(utxo)}")
    print(f"Alice's initial balance: {_kwt_str(utxo.balance(alice.public))}")
    print(f"Bob's initial balance:   {_kwt_str(utxo.balance(bob.public))}")
    print()

    # Alice sends 50 KWT to Bob, with change back to herself.
    payment = 50 * KWARTS_PER_KWT
    tx = Transaction.create(
        inputs_to_spend={genesis_outpoint: genesis_output},
        recipients=[(payment, bob.public)],
        signer=alice,
        change_pubkey=alice.public,
    )

    tx_id = txid(tx)
    total_in = sum(utxo[tx_in.outpoint].value for tx_in in tx.inputs)
    total_out = sum(out.value for out in tx.outputs)
    fee = total_in - total_out
    violations = validate_tx(tx, utxo)
    print(f"Transaction txid: {tx_id}")
    print(f"Fee:              {_kwt_str(fee)}")
    print(f"Violations:       {violations}")
    print()

    utxo.apply_transaction(tx)
    print(f"UTXO set size after apply: {len(utxo)}")
    print(f"Alice's balance: {_kwt_str(utxo.balance(alice.public))}")
    print(f"Bob's balance:   {_kwt_str(utxo.balance(bob.public))}")
    print()

    # Attempt a double-spend by reusing the now-spent genesis input.
    double_spend = Transaction.create(
        inputs_to_spend={genesis_outpoint: genesis_output},
        recipients=[(10 * KWARTS_PER_KWT, bob.public)],
        signer=alice,
        change_pubkey=alice.public,
    )
    try:
        utxo.apply_transaction(double_spend)
        print("Double-spend was incorrectly accepted!")
    except ValueError as exc:
        print(f"Double-spend rejected: {exc}")


if __name__ == "__main__":
    main()

