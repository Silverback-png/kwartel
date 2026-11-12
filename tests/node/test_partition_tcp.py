"""Tests for the partition + reorg scenario over real TCP connections."""

import asyncio
import time

from kwartel.crypto.keys import generate_keypair
from kwartel.node.cluster import Cluster
from kwartel.node.wallet import Wallet
from kwartel.transaction.model import KWARTS_PER_KWT


def _run(coro, timeout: float = 30.0):
    return asyncio.run(asyncio.wait_for(coro, timeout))


async def _wait_for(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


def test_partition_and_heal_tcp(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            b = await cluster.add_node()
            c = await cluster.add_node()
            await cluster.connect_mesh()

            ka, kb, kc = generate_keypair(), generate_keypair(), generate_keypair()
            bob = generate_keypair()

            # Act 1: fund each node; converge.
            await a.mine(ka.public)
            assert await cluster.wait_until_converged(10.0)
            await b.mine(kb.public)
            assert await cluster.wait_until_converged(10.0)
            await c.mine(kc.public)
            assert await cluster.wait_until_converged(10.0)
            assert a.height() == b.height() == c.height() == 3

            # Act 2: Alice (ka) pays Bob 30 KWT; mine the payment; converge.
            Wallet(ka).send_to(a, bob.public, 30 * KWARTS_PER_KWT)
            await a.mine(ka.public)
            assert await cluster.wait_until_converged(10.0)
            assert a.height() == b.height() == c.height() == 4
            assert b.balance(bob.public) == 30 * KWARTS_PER_KWT

            # Act 3: partition {A} | {B, C}; A mines 2, B/C mine 3.
            await cluster.partition([[a], [b, c]])
            await a.mine(ka.public)
            await a.mine(ka.public)

            await b.mine(kb.public)
            assert await _wait_for(lambda: c.height() == 5)
            await c.mine(kc.public)
            assert await _wait_for(lambda: b.height() == 6)
            await b.mine(kb.public)
            assert await _wait_for(lambda: c.height() == 7)

            assert a.height() == 6
            assert b.height() == 7
            assert c.height() == 7
            assert a.tip_hash() != b.tip_hash()

            # Act 4: heal; reconnect; converge on B/C's longer chain.
            await cluster.heal()
            assert await cluster.wait_until_converged(10.0)
            assert a.height() == b.height() == c.height() == 7
            assert a.tip_hash() == b.tip_hash() == c.tip_hash()
            assert a.balance(ka.public) == b.balance(ka.public) == c.balance(ka.public)
            assert a.balance(bob.public) == 30 * KWARTS_PER_KWT
        finally:
            await cluster.stop_all()

    _run(body())
