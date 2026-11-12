"""Tests for initial block download (SyncPlanner + integration)."""

import asyncio
import hashlib
import struct
import time
from dataclasses import replace

from kwartel.blockchain.block import Block, block_hash
from kwartel.blockchain.genesis import GENESIS_HASH
from kwartel.blockchain.persistence import serialize_block
from kwartel.crypto.keys import generate_keypair
from kwartel.net.framing import read_message, write_message
from kwartel.net.handshake import handshake_as_responder
from kwartel.node.cluster import Cluster
from kwartel.node.discovery import serialize_peers
from kwartel.node.sync import SyncPlanner
from kwartel.node.wallet import Wallet
from kwartel.transaction.model import KWARTS_PER_KWT

_U64 = struct.Struct("<Q")


def _run(coro, timeout: float = 60.0):
    return asyncio.run(asyncio.wait_for(coro, timeout))


async def _wait_for(predicate, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


# -- SyncPlanner (pure) -----------------------------------------------------


def test_plan_requests_tallest_tier():
    planner = SyncPlanner()
    known = set()
    statuses = {b"A": (10, "t10"), b"B": (5, "t5")}
    assert planner.plan(0, statuses, known.__contains__) == [(b"A", "t10")]


def test_plan_skips_known_tip():
    planner = SyncPlanner()
    known = {"t10"}
    statuses = {b"A": (10, "t10"), b"B": (10, "t10")}
    assert planner.plan(0, statuses, known.__contains__) == []


def test_plan_skips_inflight_duplicate():
    planner = SyncPlanner()
    known = set()
    statuses = {b"A": (10, "t10"), b"B": (10, "t10")}
    assert planner.plan(0, statuses, known.__contains__) == [(b"A", "t10")]
    # B's tip is the same and already in flight -> nothing new.
    assert planner.plan(0, statuses, known.__contains__) == []


def test_expire_drops_timed_out():
    planner = SyncPlanner(request_timeout=1.0)
    planner.plan(0, {b"A": (10, "t10")}, set().__contains__)
    future = time.monotonic() + 10.0
    assert planner.expire(now=future) == [("t10", b"A")]
    assert planner.in_flight == {}


def test_plan_retries_after_timeout():
    planner = SyncPlanner(request_timeout=1.0)
    planner.plan(0, {b"A": (10, "t10"), b"B": (10, "t10")}, set().__contains__)
    assert planner.expire(now=time.monotonic() + 10.0) == [("t10", b"A")]
    # caller dropped A; B is now the only candidate.
    assert planner.plan(0, {b"B": (10, "t10")}, set().__contains__) == [(b"B", "t10")]


def test_is_done():
    planner = SyncPlanner()
    assert planner.is_done(10, "t10", {b"A": (10, "t10")}) is True
    assert planner.is_done(5, "t5", {b"A": (10, "t10")}) is False


async def _start_mute(host, port, listen_port, advertise_height, advertise_tip, peers_payload):
    """A raw server that handshakes, answers STATUS/PEERS, but never GET_BLOCK."""
    node_id = hashlib.sha256(b"mute").digest()
    genesis = bytes.fromhex(GENESIS_HASH)

    async def handler(reader, writer):
        try:
            await handshake_as_responder(
                reader,
                writer,
                node_id=node_id,
                genesis_hash=genesis,
                listen_port=listen_port,
                timeout=5,
            )
            while True:
                msg = await read_message(reader, timeout=10)
                if msg is None:
                    break
                if msg.topic == "GET_STATUS":
                    await write_message(
                        writer,
                        "STATUS",
                        _U64.pack(advertise_height) + bytes.fromhex(advertise_tip),
                        timeout=5,
                    )
                elif msg.topic == "GET_PEERS":
                    await write_message(writer, "PEERS", peers_payload, timeout=5)
                # GET_BLOCK (and anything else): mute — never reply.
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    return await asyncio.start_server(handler, host, port)


def test_ibd_fresh_node(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            b = await cluster.add_node()
            c = await cluster.add_node()
            await cluster.connect_mesh()

            miners = [generate_keypair() for _ in range(3)]
            bob = generate_keypair()

            await a.mine(miners[0].public)  # block 1: fund miner_a
            assert await cluster.wait_until_converged(20.0)
            Wallet(miners[0]).send_to(a, bob.public, 10 * KWARTS_PER_KWT)
            for i in range(9):  # blocks 2..10
                node = cluster.nodes[i % 3]
                await node.mine(miners[i % 3].public)
                assert await cluster.wait_until_converged(20.0)

            assert a.height() == 10
            assert a.balance(bob.public) == 10 * KWARTS_PER_KWT

            d = await cluster.add_node(configured_peers=[("127.0.0.1", a.port)])
            assert await _wait_for(
                lambda: d.height() == 10 and d.tip_hash() == a.tip_hash()
            )
            assert d.balance(bob.public) == 10 * KWARTS_PER_KWT
        finally:
            await cluster.stop_all()

    _run(body())


def test_ibd_picks_tallest(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            b = await cluster.add_node()
            miner_a = generate_keypair()
            miner_b = generate_keypair()
            for _ in range(3):
                await a.mine(miner_a.public)
            for _ in range(5):
                await b.mine(miner_b.public)
            assert a.height() == 3 and b.height() == 5

            d = await cluster.add_node(
                configured_peers=[("127.0.0.1", a.port), ("127.0.0.1", b.port)]
            )
            assert await _wait_for(
                lambda: d.height() == 5 and d.tip_hash() == b.tip_hash()
            )
        finally:
            await cluster.stop_all()

    _run(body())


def test_no_ibd_shortcut(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        try:
            a = await cluster.add_node()
            b = await cluster.add_node()
            await cluster.connect_mesh()
            miner = generate_keypair()
            block1 = await a.mine(miner.public)
            assert await cluster.wait_until_converged(20.0)

            d = await cluster.add_node(configured_peers=[("127.0.0.1", a.port)])
            assert await _wait_for(lambda: d.peer_count() >= 1)

            # A block with identical structure but PoW that no longer meets the
            # (raised) difficulty: chain.add_block must reject it.
            bad_header = replace(block1.header, difficulty=100)
            bad_block = Block(header=bad_header, transactions=block1.transactions)
            await a.server.broadcast("BLOCK", serialize_block(bad_block))

            assert await _wait_for(
                lambda: d.height() == 1 and d.tip_hash() == a.tip_hash()
            )
            assert d.store.has_block(block_hash(bad_header)) is False
        finally:
            await cluster.stop_all()

    _run(body())


def test_sync_timeout_retry(tmp_path):
    async def body():
        cluster = Cluster(tmp_path)
        mute = None
        try:
            b = await cluster.add_node()
            miner = generate_keypair()
            for _ in range(5):
                await b.mine(miner.public)
            assert b.height() == 5

            # Mute peer advertises B's exact tip and B's address, but never
            # answers GET_BLOCK, forcing D to time out and retry via B.
            mute = await _start_mute(
                "127.0.0.1",
                0,
                9000,
                5,
                b.tip_hash(),
                serialize_peers([("127.0.0.1", b.port)]),
            )
            mute_port = mute.sockets[0].getsockname()[1]

            d = await cluster.add_node(
                configured_peers=[("127.0.0.1", mute_port)],
                sync_request_timeout=0.5,
                sync_tick=0.05,
            )
            assert await _wait_for(
                lambda: d.height() == 5 and d.tip_hash() == b.tip_hash()
            )
        finally:
            await cluster.stop_all()
            if mute is not None:
                mute.close()
                await mute.wait_closed()

    _run(body())
