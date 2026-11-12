"""Phase 2 Task 01 demo: two TCP nodes handshake and exchange a ping/pong."""

from __future__ import annotations

import asyncio
import os

from kwartel.blockchain.genesis import GENESIS_HASH
from kwartel.net.config import NetConfig
from kwartel.net.server import Server


async def main() -> None:
    genesis = bytes.fromhex(GENESIS_HASH)
    node_a = Server(NetConfig(port=9371), os.urandom(32), genesis)
    node_b = Server(NetConfig(port=9372), os.urandom(32), genesis)

    print("PHASE 2 TASK 01 - TCP wire protocol + handshake demo")
    print()
    try:
        await node_a.start()
        await node_b.start()
        print(f"  node A listening on 127.0.0.1:{node_a.port}")
        print(f"  node B listening on 127.0.0.1:{node_b.port}")

        print()
        print("Act 1: A connects to B, handshake")
        peer = await node_a.connect_peer("127.0.0.1", node_b.port)
        await _wait_for(lambda: node_b.peer_count() == 1)
        print(f"  A learned B's node_id: {peer.node_id.hex()}")
        print(
            f"  A peer_count={node_a.peer_count()}, B peer_count={node_b.peer_count()}"
        )

        print()
        print("Act 2: A pings B, B replies pong")
        await node_a.send_to(peer.node_id, "PING", b"hello from A")
        ping = await node_b.receive(timeout=5)
        assert ping is not None and ping.topic == "PING", "B did not receive PING"
        print(f"  B received PING: {ping.payload.decode()}")

        await node_b.send_to(ping.node_id, "PONG", b"hello from B")
        pong = await node_a.receive(timeout=5)
        assert pong is not None and pong.topic == "PONG", "A did not receive PONG"
        print(f"  A received PONG: {pong.payload.decode()}")

        print()
        print("PHASE 2 TASK 01 COMPLETE: handshake + ping/pong over TCP.")
    finally:
        await node_a.stop()
        await node_b.stop()


async def _wait_for(predicate, timeout: float = 5.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met within timeout")


if __name__ == "__main__":
    asyncio.run(main())
