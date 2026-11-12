"""Peer discovery: address book + GET_PEERS/PEERS wire codec.

The address book is persisted to JSON so a restarting node remembers peers it has
learned.  All wire parsing is strict: malformed PEERS payloads raise so the
caller can disconnect the offending peer.
"""

from __future__ import annotations

import json
import random
import struct
from dataclasses import dataclass
from pathlib import Path

_U16 = struct.Struct("<H")
_U8 = struct.Struct("<B")

MAX_PEERS_PER_MESSAGE = 64
MAX_HOST_LEN = 253
ADDRESS_BOOK_CAP = 1000
MAX_FAILURES = 5
MAX_NEW_CONNECTIONS_PER_BATCH = 2
DISCOVERY_INTERVAL = 30.0


@dataclass
class AddressEntry:
    """One known peer address with provenance and failure tracking."""

    host: str
    port: int
    source: str  # "configured" | "peer" | "observed"
    failures: int = 0


class AddressBook:
    """A bounded, deduplicated set of known peer addresses."""

    def __init__(self, max_entries: int = ADDRESS_BOOK_CAP) -> None:
        self.max_entries = max_entries
        self._entries: dict[tuple[str, int], AddressEntry] = {}

    def add(self, host: str, port: int, source: str) -> bool:
        """Add an address; dedup on (host, port). Returns False if rejected."""
        port = int(port)
        key = (host, port)
        if key in self._entries:
            return False
        if len(self._entries) >= self.max_entries:
            if not self._evict_one():
                return False
        self._entries[key] = AddressEntry(host=host, port=port, source=source)
        return True

    def _evict_one(self) -> bool:
        # Evict the oldest non-configured entry, preferring "peer" over
        # "observed"; configured entries are never evicted.
        for source in ("peer", "observed"):
            for key, entry in self._entries.items():
                if entry.source == source:
                    del self._entries[key]
                    return True
        return False  # only configured entries remain

    def mark_failed(self, host: str, port: int) -> None:
        """Increment failures; drop non-configured entries at the threshold."""
        key = (host, int(port))
        entry = self._entries.get(key)
        if entry is None:
            return
        entry.failures += 1
        if entry.source != "configured" and entry.failures >= MAX_FAILURES:
            del self._entries[key]

    def get_batch(self, n: int, exclude: set | None = None) -> list[tuple[str, int]]:
        """Return up to ``n`` random distinct (host, port) tuples not in exclude."""
        exclude = exclude or set()
        candidates = [key for key in self._entries if key not in exclude]
        if n >= len(candidates):
            return list(candidates)
        return random.sample(candidates, n)

    def all(self) -> list[tuple[str, int]]:
        return list(self._entries.keys())

    def source_of(self, host: str, port: int) -> str | None:
        """Return the recorded source for an address, or None if unknown."""
        entry = self._entries.get((host, int(port)))
        return entry.source if entry is not None else None

    def __len__(self) -> int:
        return len(self._entries)

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "host": e.host,
                "port": e.port,
                "source": e.source,
                "failures": e.failures,
            }
            for e in self._entries.values()
        ]
        with open(path, "w") as f:
            json.dump(data, f)

    def load(self, path) -> None:
        """Load from JSON; a corrupt/missing file yields an empty book."""
        path = Path(path)
        if not path.exists():
            return
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, ValueError):
            return
        if not isinstance(data, list):
            return
        for item in data:
            if not isinstance(item, dict):
                continue
            host = item.get("host")
            port = item.get("port")
            if not isinstance(host, str) or not isinstance(port, int):
                continue
            if not (1 <= port <= 65535):
                continue
            source = item.get("source", "peer")
            if source not in ("configured", "peer", "observed"):
                source = "peer"
            failures = item.get("failures", 0)
            self._entries[(host, port)] = AddressEntry(
                host=host, port=port, source=source, failures=int(failures)
            )


def serialize_peers(addrs) -> bytes:
    """Encode a list of (host, port) as a PEERS payload (capped at 64)."""
    addrs = list(addrs)[:MAX_PEERS_PER_MESSAGE]
    out = [_U16.pack(len(addrs))]
    for host, port in addrs:
        host_bytes = host.encode("ascii")[:MAX_HOST_LEN]
        out.append(_U8.pack(len(host_bytes)))
        out.append(host_bytes)
        out.append(_U16.pack(int(port)))
    return b"".join(out)


def deserialize_peers(payload: bytes) -> list[tuple[str, int]]:
    """Decode a PEERS payload; raise ValueError on any malformed structure."""
    if len(payload) < 2:
        raise ValueError("PEERS payload too short")
    (count,) = _U16.unpack_from(payload, 0)
    if count > MAX_PEERS_PER_MESSAGE:
        raise ValueError(f"PEERS count {count} exceeds cap {MAX_PEERS_PER_MESSAGE}")
    off = 2
    addrs: list[tuple[str, int]] = []
    for _ in range(count):
        if off >= len(payload):
            raise ValueError("truncated PEERS payload")
        host_len = payload[off]
        off += 1
        if host_len == 0 or host_len > MAX_HOST_LEN:
            raise ValueError(f"invalid host length {host_len}")
        if off + host_len + 2 > len(payload):
            raise ValueError("truncated host or port")
        host = payload[off : off + host_len].decode("ascii")
        off += host_len
        (port,) = _U16.unpack_from(payload, off)
        off += 2
        if port < 1:
            raise ValueError("port must be >= 1")
        addrs.append((host, port))
    if off != len(payload):
        raise ValueError("trailing bytes in PEERS payload")
    return addrs
