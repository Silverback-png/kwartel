"""Tests for the partition + reorg scenario across three nodes."""

from kwartel.crypto.keys import generate_keypair
from kwartel.node.miner import mine_once
from kwartel.node.network import NetworkBus
from kwartel.node.node import FullNode
from kwartel.node.wallet import Wallet
from kwartel.transaction.model import KWARTS_PER_KWT


def _sync(bus, nodes, rounds=100):
    for _ in range(rounds):
        bus.flush()
        processed = sum(n.handle_messages() for n in nodes)
        if processed == 0 and bus.pending_count() == 0:
            break


def test_partition_and_reorg(tmp_path):
    bus = NetworkBus()
    a = FullNode("A", tmp_path / "A.db", bus)
    b = FullNode("B", tmp_path / "B.db", bus)
    c = FullNode("C", tmp_path / "C.db", bus)
    nodes = [a, b, c]

    ka, kb, kc = generate_keypair(), generate_keypair(), generate_keypair()
    bob = generate_keypair()

    # Act 1: fund each node with one block; converge.
    mine_once(a, ka.public)
    _sync(bus, nodes)
    mine_once(b, kb.public)
    _sync(bus, nodes)
    mine_once(c, kc.public)
    _sync(bus, nodes)
    assert a.height() == b.height() == c.height() == 3

    # Act 2: Alice (ka) pays Bob 30 KWT; mine the payment; converge.
    Wallet(ka).send_to(a, bob.public, 30 * KWARTS_PER_KWT)
    _sync(bus, nodes)
    mine_once(a, ka.public)
    _sync(bus, nodes)
    assert a.height() == b.height() == c.height() == 4
    assert b.balance(bob.public) == 30 * KWARTS_PER_KWT

    # Act 3: partition A | B,C. A mines 2, B/C mine 3.
    bus.partition([{"A"}, {"B", "C"}])
    mine_once(a, ka.public)
    mine_once(a, ka.public)

    mine_once(b, kb.public)
    bus.flush()
    c.handle_messages()
    mine_once(c, kc.public)
    bus.flush()
    b.handle_messages()
    mine_once(b, kb.public)
    bus.flush()
    c.handle_messages()

    assert a.height() == 6
    assert b.height() == 7
    assert c.height() == 7
    assert a.tip_hash() != b.tip_hash()

    ka_balance_during_partition = a.balance(ka.public)

    # Act 4: heal; announce tips; sync to quiescence.
    bus.heal()
    a.announce_tip()
    b.announce_tip()
    c.announce_tip()
    _sync(bus, nodes, rounds=200)

    # All nodes converge on B/C's longer chain.
    assert a.height() == b.height() == c.height() == 7
    assert a.tip_hash() == b.tip_hash() == c.tip_hash()

    # Node A's balances changed to the fork reality (orphaned A-fork coinbases gone).
    assert a.balance(ka.public) == b.balance(ka.public) == c.balance(ka.public)
    assert a.balance(ka.public) < ka_balance_during_partition

    # Bob's payment survived (it was in the common ancestor).
    assert a.balance(bob.public) == 30 * KWARTS_PER_KWT
