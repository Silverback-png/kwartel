"""Tests for kwartel.node.network."""

from kwartel.node.network import NetworkBus


def test_register_returns_mailbox():
    bus = NetworkBus()
    mb = bus.register("A")
    assert mb.node_id == "A"


def test_send_delivers_to_others_on_flush():
    bus = NetworkBus()
    a = bus.register("A")
    b = bus.register("B")
    c = bus.register("C")
    a.send("TX", b"hello")
    bus.flush()
    assert b.drain()[0].payload == b"hello"
    assert c.drain()[0].payload == b"hello"
    # sender does not receive its own message
    assert a.drain() == []


def test_drain_clears_inbox():
    bus = NetworkBus()
    a = bus.register("A")
    b = bus.register("B")
    a.send("BLOCK", b"data")
    bus.flush()
    assert len(b.drain()) == 1
    assert b.drain() == []


def test_message_has_topic_payload_sender():
    bus = NetworkBus()
    a = bus.register("A")
    b = bus.register("B")
    a.send("INV_BLOCK", b"\x01\x02")
    bus.flush()
    msg = b.drain()[0]
    assert msg.topic == "INV_BLOCK"
    assert msg.payload == b"\x01\x02"
    assert msg.sender == "A"


def test_partition_blocks_cross_group():
    bus = NetworkBus()
    a = bus.register("A")
    b = bus.register("B")
    c = bus.register("C")
    bus.partition([{"A"}, {"B", "C"}])
    a.send("BLOCK", b"from_a")
    b.send("BLOCK", b"from_b")
    bus.flush()
    # A's message must not reach B (different group)
    assert b.drain() == []
    # B's message must not reach A (different group)
    assert a.drain() == []
    # B's message reaches C (same group)
    assert [m.payload for m in c.drain()] == [b"from_b"]

    # within group B/C, delivery still works
    b.send("TX", b"within")
    bus.flush()
    assert [m.payload for m in c.drain()] == [b"within"]
    assert b.drain() == []


def test_heal_restores_delivery():
    bus = NetworkBus()
    a = bus.register("A")
    b = bus.register("B")
    bus.partition([{"A"}, {"B"}])
    a.send("BLOCK", b"before_heal")
    bus.flush()
    assert b.drain() == []

    bus.heal()
    a.send("BLOCK", b"after_heal")
    bus.flush()
    assert b.drain()[0].payload == b"after_heal"
