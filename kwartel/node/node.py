"""Full node: chain + mempool + network participation for Kwartel."""

from __future__ import annotations

from pathlib import Path

from kwartel.blockchain.block import block_hash
from kwartel.blockchain.chain import Chain
from kwartel.blockchain.persistence import BlockStore
from kwartel.node.gossip import handle_message
from kwartel.node.network import Message, NetworkBus
from kwartel.transaction.mempool import Mempool
from kwartel.transaction.model import Transaction, serialize_tx


class FullNode:
    """A node with its own chain, mempool, and mailbox on the bus."""

    def __init__(self, node_id: str, db_path: Path, bus: NetworkBus) -> None:
        self.node_id = node_id
        self.store = BlockStore(db_path)
        self.chain = Chain(self.store)
        self.mempool = Mempool()
        self.mailbox = bus.register(node_id)
        self._pending: dict = {}

    # -- public API ---------------------------------------------------------

    def submit_tx(self, tx: Transaction) -> bool:
        if self.mempool.accept(tx, self.chain.utxo_set()):
            self.mailbox.send("TX", serialize_tx(tx, include_signatures=True))
            return True
        return False

    def handle_messages(self) -> int:
        count = 0
        for msg in self.mailbox.drain():
            count += 1
            self._handle(msg)
        return count

    def height(self) -> int:
        return self.chain.height()

    def tip_hash(self) -> str:
        return block_hash(self.chain.tip().header)

    def balance(self, pubkey: bytes) -> int:
        return self.chain.balance(pubkey)

    def announce_tip(self) -> None:
        self.mailbox.send("INV_BLOCK", bytes.fromhex(self.tip_hash()))

    # -- message handling ---------------------------------------------------

    def _handle(self, msg: Message) -> None:
        for topic, payload in handle_message(
            self.store, self.chain, self.mempool, self._pending, msg.topic, msg.payload
        ):
            self.mailbox.send(topic, payload)
