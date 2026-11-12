"""Tests for block/tx gossip over TCP (Phase 2 Task 02)."""

import asyncio
import time

from kwartel.blockchain.block import block_hash
from kwartel.crypto.keys import generate_keypair
from kwartel.node.cluster import Cluster
from kwartel.node.netnode import NetNode
from kwartel.node.wallet import Wallet
from kwartel.transaction.model import KWARTS_PER_KWT, txid


def _run(coro, timeout: float = 30.0):
    return asyncio.run(asyncio.wait_for(coro, timeout))


async def _wait_for(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


def test_two_nodes_sync_block(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            b = await cluster.add_node()
            await cluster.connect_mesh()

            miner = generate_keypair()
            block = await a.mine(miner.public)
            assert block is not None
            assert await cluster.wait_until_converged(10.0)
            assert a.height() == b.height() == 1
            assert a.tip_hash() == b.tip_hash() == block_hash(block.header)
        finally:
            await cluster.stop_all()

    _run(body())


def test_tx_propagates_and_gets_mined(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            b = await cluster.add_node()
            await cluster.connect_mesh()

            miner_a = generate_keypair()
            miner_b = generate_keypair()
            await a.mine(miner_a.public)
            assert await cluster.wait_until_converged(10.0)

            bob = generate_keypair()
            tx = Wallet(miner_a).send_to(a, bob.public, 10 * KWARTS_PER_KWT)
            assert await _wait_for(lambda: b.mempool.get(txid(tx)) is not None)

            await b.mine(miner_b.public)
            assert await cluster.wait_until_converged(10.0)
            assert a.balance(bob.public) == b.balance(bob.public) == 10 * KWARTS_PER_KWT
        finally:
            await cluster.stop_all()

    _run(body())


def test_orphan_rescue(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            # A mines N+1 and N+2 in isolation (B has not connected yet).
            a = await cluster.add_node()
            miner = generate_keypair()
            await a.mine(miner.public)
            await a.mine(miner.public)
            assert a.height() == 2

            # B connects and first receives A's tip (N+2) via STATUS -> GET_BLOCK,
            # which is an orphan; the orphan buffer must fetch N+1 to recover.
            b = await cluster.add_node()
            await b.connect("127.0.0.1", a.port)
            assert await _wait_for(lambda: b.height() == 2 and b.tip_hash() == a.tip_hash())
        finally:
            await cluster.stop_all()

    _run(body())


def test_linear_topology_multihop(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            b = await cluster.add_node()
            c = await cluster.add_node()
            await cluster.connect_linear()  # A -> B -> C

            miner = generate_keypair()
            await a.mine(miner.public)
            assert await cluster.wait_until_converged(10.0)
            assert a.height() == b.height() == c.height() == 1
            assert a.tip_hash() == b.tip_hash() == c.tip_hash()
        finally:
            await cluster.stop_all()

    _run(body())


def test_hostile_block_dropped(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            b = await cluster.add_node()
            await cluster.connect_mesh()
            assert await _wait_for(lambda: a.peer_count() == 1 and b.peer_count() == 1)

            miner = generate_keypair()
            await a.mine(miner.public)
            assert await cluster.wait_until_converged(10.0)

            # B sends garbage bytes as a BLOCK; A must disconnect it, not crash.
            await b.server.broadcast("BLOCK", b"garbage")
            assert await _wait_for(lambda: a.peer_count() == 0)

            # A is still alive and can still mine.
            await a.mine(miner.public)
            assert a.height() == 2
        finally:
            await cluster.stop_all()

    _run(body())


def test_status_exchange(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            miner = generate_keypair()
            await a.mine(miner.public)
            await a.mine(miner.public)
            assert a.height() == 2

            b = await cluster.add_node()
            await b.connect("127.0.0.1", a.port)
            assert await _wait_for(lambda: a.node_id in b.peer_statuses)
            assert b.peer_statuses[a.node_id] == (a.height(), a.tip_hash())
        finally:
            await cluster.stop_all()

    _run(body())
