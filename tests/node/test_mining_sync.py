"""Tests for kwartel.node.miner."""

from kwartel.blockchain.block import block_hash
from kwartel.crypto.keys import generate_keypair
from kwartel.node.miner import mine_once
from kwartel.node.network import NetworkBus
from kwartel.node.node import FullNode
from kwartel.node.wallet import Wallet
from kwartel.transaction.model import KWARTS_PER_KWT, txid
from kwartel.transaction.validation import is_coinbase


def _sync(bus, nodes, rounds=30):
    for _ in range(rounds):
        bus.flush()
        processed = sum(n.handle_messages() for n in nodes)
        if processed == 0 and bus.pending_count() == 0:
            break


def test_mine_once_creates_coinbase_block(tmp_path):
    bus = NetworkBus()
    node = FullNode("A", tmp_path / "A.db", bus)
    miner = generate_keypair()
    block = mine_once(node, miner.public)
    assert block is not None
    assert node.height() == 1
    assert is_coinbase(block.transactions[0]) is True


def test_mine_once_includes_txs_and_clears_mempool(tmp_path):
    bus = NetworkBus()
    node = FullNode("A", tmp_path / "A.db", bus)
    miner = generate_keypair()
    mine_once(node, miner.public)  # fund miner

    bob = generate_keypair()
    wallet = Wallet(miner)
    tx = wallet.send_to(node, bob.public, 10 * KWARTS_PER_KWT)
    assert len(node.mempool) == 1

    block = mine_once(node, miner.public)
    assert block is not None
    # tx included in block and removed from mempool
    assert txid(tx) in [txid(t) for t in block.transactions]
    assert len(node.mempool) == 0


def test_mine_once_broadcasts_block(tmp_path):
    bus = NetworkBus()
    a = FullNode("A", tmp_path / "A.db", bus)
    b = FullNode("B", tmp_path / "B.db", bus)
    miner = generate_keypair()
    block = mine_once(a, miner.public)
    _sync(bus, [a, b])
    assert b.height() == 1
    assert b.tip_hash() == block_hash(block.header)
