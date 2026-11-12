"""Transport-agnostic gossip message handling for Kwartel nodes.

The message-handling logic lives here so both the in-memory bus ``FullNode``
(Phase 1) and the TCP ``NetNode`` (Phase 2) share the exact same behavior.
These functions are pure and synchronous: they mutate chain/mempool state and
RETURN the outbound messages to send, leaving the transport to deliver them.

Validation is imported from ``kwartel.blockchain`` and ``kwartel.transaction``;
nothing here re-implements consensus rules.
"""

from __future__ import annotations

from kwartel.blockchain.block import Block, block_hash
from kwartel.blockchain.persistence import deserialize_block, deserialize_tx, serialize_block
from kwartel.transaction.model import txid


def handle_message(store, chain, mempool, pending, topic, payload):
    """Process one inbound gossip message; return outbound (topic, payload)s.

    May raise ``struct.error``/``IndexError``/``ValueError`` on malformed
    deserialization; the caller decides how to treat hostile input (the bus
    trusts its peers, TCP disconnects them).
    """
    if topic == "TX":
        tx, _off = deserialize_tx(payload, 0)
        mempool.accept(tx, chain.utxo_set())
        return []
    if topic == "BLOCK":
        return handle_block(store, chain, mempool, pending, deserialize_block(payload))
    if topic == "INV_BLOCK":
        h = payload.hex()
        if not store.has_block(h):
            return [("GET_BLOCK", payload)]
        return []
    if topic == "GET_BLOCK":
        h = payload.hex()
        block = store.get_block(h)
        if block is not None:
            return [("BLOCK", serialize_block(block))]
        return []
    return []


def handle_block(store, chain, mempool, pending, block: Block):
    """Process one inbound block; return outbound messages to send."""
    h = block_hash(block.header)
    if store.has_block(h):
        return []  # duplicate, idempotent

    violations = chain.add_block(block)
    if violations:
        if any("parent" in v.lower() for v in violations):
            pending[h] = block
            return [("GET_BLOCK", bytes.fromhex(block.header.prev_block_hash))]
        return []

    return _on_block_added(mempool, block, h) + _retry_pending(
        store, chain, mempool, pending
    )


def _on_block_added(mempool, block: Block, h: str):
    for tx in block.transactions:
        mempool.remove(txid(tx))
    return [("INV_BLOCK", bytes.fromhex(h))]


def _retry_pending(store, chain, mempool, pending):
    out = []
    progressed = True
    while progressed:
        progressed = False
        for h, block in list(pending.items()):
            if not store.has_block(block.header.prev_block_hash):
                continue
            violations = chain.add_block(block)
            if not violations:
                del pending[h]
                out += _on_block_added(mempool, block, h)
                progressed = True
    return out
