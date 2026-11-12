"""Cluster helper: spin up N NetNodes, connect a topology, and tear down."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from kwartel.node.netnode import NetNode


class Cluster:
    """Manages a set of NetNodes for tests and demos."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.nodes: list[NetNode] = []
        self._edges: list[tuple[int, int]] = []

    async def add_node(self, port: int | None = None, *, configured_peers=None, **kwargs) -> NetNode:
        idx = len(self.nodes)
        node = NetNode(
            f"node{idx}",
            self.data_dir / f"node{idx}.db",
            port,
            configured_peers=configured_peers,
            **kwargs,
        )
        await node.start()
        self.nodes.append(node)
        return node

    async def connect_mesh(self) -> None:
        """Fully connect every pair (i connects to j for i < j)."""
        self._edges = []
        for i in range(len(self.nodes)):
            for j in range(i + 1, len(self.nodes)):
                await self.nodes[i].connect("127.0.0.1", self.nodes[j].port)
                self._edges.append((i, j))

    async def connect_linear(self) -> None:
        """Connect A -> B -> C only (for multi-hop tests)."""
        self._edges = []
        for i in range(len(self.nodes) - 1):
            await self.nodes[i].connect("127.0.0.1", self.nodes[i + 1].port)
            self._edges.append((i, i + 1))

    async def partition(self, groups) -> None:
        """Drop connections between groups (real connection closes)."""
        id_to_group: dict[bytes, int] = {}
        for gi, group in enumerate(groups):
            for node in group:
                id_to_group[node.node_id] = gi
        for node in self.nodes:
            my_group = id_to_group.get(node.node_id, 0)
            for peer in list(node.server.book.all()):
                if id_to_group.get(peer.node_id, my_group) != my_group:
                    await peer.close()
                    node.server.book.remove(peer)

    async def heal(self) -> None:
        """Reconnect the originally configured topology."""
        for i, j in self._edges:
            a, b = self.nodes[i], self.nodes[j]
            if a.server.book.get(b.node_id) is None:
                await a.connect("127.0.0.1", b.port)

    async def stop_all(self) -> None:
        for node in self.nodes:
            await node.stop()

    async def wait_until_converged(self, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._converged():
                return True
            await asyncio.sleep(0.05)
        return False

    def _converged(self) -> bool:
        if not self.nodes:
            return True
        heights = {n.height() for n in self.nodes}
        tips = {n.tip_hash() for n in self.nodes}
        return len(heights) == 1 and len(tips) == 1
