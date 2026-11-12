"""Phase 2 Task 02 demo: the five-act network scenario over real TCP."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from kwartel.crypto.keys import generate_keypair
from kwartel.node.cluster import Cluster
from kwartel.node.wallet import Wallet
from kwartel.transaction.model import KWARTS_PER_KWT


def _shap(kwarts: int) -> str:
    return f"{kwarts // KWARTS_PER_KWT} SHAP"


def _fresh_dir() -> Path:
    data_dir = Path("data") / "netdemo"
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in ("node0", "node1", "node2", "node3"):
        for suffix in (".db", ".db-wal", ".db-shm", ".peers.json"):
            p = data_dir / (name + suffix)
            if p.exists():
                p.unlink()
    return data_dir


async def _wait_for(predicate, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition not met within timeout")


async def main() -> None:
    cluster = Cluster(_fresh_dir())
    try:
        a = await cluster.add_node()
        b = await cluster.add_node()
        c = await cluster.add_node()
        await cluster.connect_mesh()

        ka = generate_keypair()
        kb = generate_keypair()
        kc = generate_keypair()
        bob = generate_keypair()
        wallet_a = Wallet(ka)

        print("PHASE 2 TASK 02 - three-node TCP gossip demo")
        print()
        print("Act 1: boot (full mesh)")
        for n in (a, b, c):
            print(f"  node {n.node_id_str}: height={n.height()} tip={n.tip_hash()[:16]}...")
        print(f"  converged: {await cluster.wait_until_converged(10.0)}")

        print()
        print("Act 2: funding (one block per node)")
        await a.mine(ka.public)
        await cluster.wait_until_converged(10.0)
        await b.mine(kb.public)
        await cluster.wait_until_converged(10.0)
        await c.mine(kc.public)
        await cluster.wait_until_converged(10.0)
        for n in (a, b, c):
            print(f"  node {n.node_id_str}: height={n.height()} tip={n.tip_hash()[:16]}...")
        print(f"  converged: {await cluster.wait_until_converged(10.0)}")

        print()
        print("Act 3: Alice pays Bob 30 SHAP")
        wallet_a.send_to(a, bob.public, 30 * KWARTS_PER_KWT)
        await a.mine(ka.public)
        await cluster.wait_until_converged(10.0)
        for n in (a, b, c):
            print(f"  node {n.node_id_str}: height={n.height()} bob={_shap(n.balance(bob.public))}")
        consistent = (
            a.balance(bob.public)
            == b.balance(bob.public)
            == c.balance(bob.public)
            == 30 * KWARTS_PER_KWT
        )
        print(f"  Bob balance consistent: {consistent}")

        print()
        print("Act 4: partition A | B,C")
        await cluster.partition([[a], [b, c]])
        await a.mine(ka.public)
        await a.mine(ka.public)
        await b.mine(kb.public)
        await _wait_for(lambda: c.height() == 5)
        await c.mine(kc.public)
        await _wait_for(lambda: b.height() == 6)
        await b.mine(kb.public)
        await _wait_for(lambda: c.height() == 7)
        print(f"  node {a.node_id_str}: height={a.height()} tip={a.tip_hash()[:16]}...")
        print(f"  node {b.node_id_str}: height={b.height()} tip={b.tip_hash()[:16]}...")
        print(f"  node {c.node_id_str}: height={c.height()} tip={c.tip_hash()[:16]}...")
        print(f"  competing tips (A != B): {a.tip_hash() != b.tip_hash()}")

        print()
        print("Act 5: heal and converge")
        await cluster.heal()
        converged = await cluster.wait_until_converged(20.0)
        for n in (a, b, c):
            print(f"  node {n.node_id_str}: height={n.height()} tip={n.tip_hash()[:16]}...")
        print(f"  all converged: {converged}")
        print(
            f"  Bob balance: {_shap(a.balance(bob.public))} "
            f"(consistent: {a.balance(bob.public) == b.balance(bob.public) == c.balance(bob.public)})"
        )

        print()
        print("PHASE 2 TASK 02 COMPLETE: 3 TCP nodes converged after partition + reorg.")

        print()
        print("Act 6: cold join (fresh node3 knows only node1's address)")
        node3 = await cluster.add_node(configured_peers=[("127.0.0.1", b.port)])
        await _wait_for(
            lambda: node3.height() == a.height()
            and node3.tip_hash() == a.tip_hash(),
            timeout=20.0,
        )
        for n in (a, b, c, node3):
            print(f"  node {n.node_id_str}: height={n.height()} tip={n.tip_hash()[:16]}...")
        print(
            f"  node3 synced to tip: "
            f"{node3.height() == a.height() and node3.tip_hash() == a.tip_hash()}"
        )
        print(f"  node3 Bob balance: {_shap(node3.balance(bob.public))}")

        print()
        print("PHASE 2 TASK 03 COMPLETE: fresh node cold-joined and synced to tip.")
    finally:
        await cluster.stop_all()


if __name__ == "__main__":
    asyncio.run(main())
