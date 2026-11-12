"""Mining helper for Kwartel nodes."""

from __future__ import annotations

from kwartel.blockchain.block import Block, BlockHeader, block_hash, mine_block
from kwartel.blockchain.coinbase import create_coinbase
from kwartel.blockchain.merkle import merkle_root
from kwartel.blockchain.persistence import serialize_block
from kwartel.transaction.model import txid


def build_and_add_block(chain, mempool, coinbase_pubkey: bytes) -> Block | None:
    """Construct, validate, and append one block, updating the mempool.

    Returns the block, or ``None`` if it was rejected (should not happen for a
    well-behaved node).  Transport-agnostic: the caller is responsible for
    broadcasting the serialized block.
    """
    txs = list(mempool.all_transactions())

    working = chain.utxo_set().copy()
    total_fees = 0
    for tx in txs:
        total_in = sum(working[tx_in.outpoint].value for tx_in in tx.inputs)
        total_out = sum(o.value for o in tx.outputs)
        total_fees += total_in - total_out
        working.apply_transaction(tx)

    coinbase = create_coinbase(chain.height() + 1, coinbase_pubkey, total_fees)
    block_txs = (coinbase,) + tuple(txs)
    header = BlockHeader(
        prev_block_hash=block_hash(chain.tip().header),
        merkle_root=merkle_root([txid(t) for t in block_txs]),
        timestamp=chain.tip().header.timestamp + 1,
        difficulty=8,
        nonce=0,
    )
    block = Block(mine_block(header), block_txs)

    violations = chain.add_block(block)
    if violations:
        return None

    for tx in txs:
        mempool.remove(txid(tx))
    return block


def mine_once(node, coinbase_pubkey: bytes) -> Block | None:
    """Mine one block on ``node`` (bus transport) and broadcast it.

    Returns the mined block, or ``None`` if it was rejected.
    """
    block = build_and_add_block(node.chain, node.mempool, coinbase_pubkey)
    if block is not None:
        node.mailbox.send("BLOCK", serialize_block(block))
    return block
