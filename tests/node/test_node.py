"""Tests for kwartel.node.node."""

from kwartel.blockchain.block import block_hash
from kwartel.blockchain.persistence import serialize_block
from kwartel.crypto.keys import generate_keypair
from kwartel.node.miner import mine_once
from kwartel.node.network import NetworkBus
from kwartel.node.node import FullNode
from kwartel.node.wallet import Wallet
from kwartel.transaction.model import Transaction, txid


def _sync(bus, nodes, rounds=30):
    for _ in range(rounds):
        bus.flush()
        processed = sum(n.handle_messages() for n in nodes)
        if processed == 0 and bus.pending_count() == 0:
            break


def test_submit_invalid_tx_returns_false(tmp_path):
    bus = NetworkBus()
    node = FullNode("A", tmp_path / "A.db", bus)
    bad = Transaction(inputs=(), outputs=())
    assert node.submit_tx(bad) is False


def test_tx_propagation(tmp_path):
    bus = NetworkBus()
    a = FullNode("A", tmp_path / "A.db", bus)
    b = FullNode("B", tmp_path / "B.db", bus)
    miner_a = generate_keypair()
    mine_once(a, miner_a.public)
    _sync(bus, [a, b])

    bob = generate_keypair()
    tx = Wallet(miner_a).send_to(a, bob.public, 10)
    _sync(bus, [a, b])
    assert b.mempool.get(txid(tx)) is not None


def test_block_propagation(tmp_path):
    bus = NetworkBus()
    a = FullNode("A", tmp_path / "A.db", bus)
    b = FullNode("B", tmp_path / "B.db", bus)
    miner = generate_keypair()
    block = mine_once(a, miner.public)
    _sync(bus, [a, b])
    assert a.height() == b.height() == 1
    assert a.tip_hash() == b.tip_hash() == block_hash(block.header)


def test_duplicate_block_idempotent(tmp_path):
    bus = NetworkBus()
    a = FullNode("A", tmp_path / "A.db", bus)
    b = FullNode("B", tmp_path / "B.db", bus)
    miner = generate_keypair()
    block = mine_once(a, miner.public)
    _sync(bus, [a, b])
    h_before = b.height()

    # Re-deliver the same block; must not change height or crash.
    a.mailbox.send("BLOCK", serialize_block(block))
    _sync(bus, [a, b])
    assert b.height() == h_before


def test_inv_get_handshake(tmp_path):
    bus = NetworkBus()
    a = FullNode("A", tmp_path / "A.db", bus)
    b = FullNode("B", tmp_path / "B.db", bus)
    miner = generate_keypair()
    block = mine_once(a, miner.public)

    # Simulate B missing the BLOCK broadcast: deliver then discard.
    bus.flush()
    b.mailbox.drain()
    assert b.height() == 0

    # A announces its tip; the INV/GET handshake fetches the missing block.
    a.announce_tip()
    _sync(bus, [a, b], rounds=30)
    assert b.height() == 1
    assert b.tip_hash() == block_hash(block.header)
