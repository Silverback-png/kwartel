"""Configuration for the Kwartel TCP networking layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NetConfig:
    """Networking parameters for a single node.

    ``port`` is required (there is no sensible default); the rest have safe
    defaults.  A ``port`` of 0 asks the OS for an ephemeral port, which the test
    suite uses to avoid collisions.
    """

    port: int
    host: str = "127.0.0.1"
    max_peers: int = 16
    handshake_timeout: float = 10.0
    idle_timeout: float = 30.0
