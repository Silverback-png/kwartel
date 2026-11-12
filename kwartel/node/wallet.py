"""Thin wallet wrapper over Kwartel's crypto and a node."""

from __future__ import annotations

from kwartel.crypto.keys import KeyPair, address
from kwartel.node.node import FullNode
from kwartel.transaction.model import Transaction


class Wallet:
    """Holds a keypair and builds transactions against a node's UTXO set."""

    def __init__(self, keypair: KeyPair) -> None:
        self.kp = keypair

    @property
    def public(self) -> bytes:
        return self.kp.public

    def new_address(self) -> str:
        return address(self.kp.public)

    def balance(self, node: FullNode) -> int:
        return node.balance(self.kp.public)

    def send_to(
        self, node: FullNode, recipient_pubkey: bytes, amount_kwarts: int
    ) -> Transaction:
        """Build and submit a transaction paying ``recipient_pubkey``.

        Gathers this wallet's spendable outputs from the node's UTXO set, selects
        until ``amount_kwarts`` is covered, and returns change to itself.  Raises
        ``ValueError`` on insufficient funds or rejection.
        """
        utxo = node.chain.utxo_set()
        inputs: dict = {}
        total = 0
        for outpoint, output in utxo.items():
            if output.lock == self.kp.public:
                inputs[outpoint] = output
                total += output.value
                if total >= amount_kwarts:
                    break

        if total < amount_kwarts:
            raise ValueError("insufficient funds")

        tx = Transaction.create(
            inputs_to_spend=inputs,
            recipients=[(amount_kwarts, recipient_pubkey)],
            signer=self.kp,
            change_pubkey=self.kp.public,
        )
        if not node.submit_tx(tx):
            raise ValueError("transaction rejected by node")
        return tx
