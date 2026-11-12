"""Initial block download (IBD) state machine.

The SyncPlanner is pure and socket-free: it decides WHICH block hashes to request
from WHICH peers, tracks in-flight requests with timeouts, and detects when sync
is complete.  It never validates blocks itself — every block still flows through
``chain.add_block`` via the normal gossip path (no trust shortcut).
"""

from __future__ import annotations

import time

MAX_IN_FLIGHT = 8
REQUEST_TIMEOUT = 30.0


class SyncPlanner:
    """Decides block requests for initial download; tracks in-flight requests."""

    def __init__(
        self,
        max_in_flight: int = MAX_IN_FLIGHT,
        request_timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        self.max_in_flight = max_in_flight
        self.request_timeout = request_timeout
        # block_hash -> (deadline, peer_id)
        self.in_flight: dict[str, tuple[float, bytes]] = {}

    def plan(
        self,
        my_height: int,
        peer_statuses: dict[bytes, tuple[int, str]],
        has_block,
    ) -> list[tuple[bytes, str]]:
        """Return (peer_id, block_hash) requests to issue now; track them.

        Only the tallest peer tier is considered; up to ``max_in_flight`` tips
        are requested (distinct tips only, e.g. a fork).  A tip already known or
        already in flight is skipped.
        """
        # Drop in-flight entries whose block is now known.
        self.in_flight = {
            h: v for h, v in self.in_flight.items() if not has_block(h)
        }

        taller = [
            (pid, height, tip)
            for pid, (height, tip) in peer_statuses.items()
            if height > my_height
        ]
        if not taller:
            return []
        tallest = max(height for _, height, _ in taller)

        requests: list[tuple[bytes, str]] = []
        for peer_id, height, tip in taller:
            if height != tallest:
                continue  # only the tallest tier
            if has_block(tip) or tip in self.in_flight:
                continue
            if len(self.in_flight) + len(requests) >= self.max_in_flight:
                break
            self.in_flight[tip] = (time.monotonic() + self.request_timeout, peer_id)
            requests.append((peer_id, tip))
        return requests

    def expire(self, now: float | None = None) -> list[tuple[str, bytes]]:
        """Return (block_hash, peer_id) whose deadline passed; drop them."""
        now = time.monotonic() if now is None else now
        expired = [
            (h, peer_id)
            for h, (deadline, peer_id) in self.in_flight.items()
            if deadline < now
        ]
        for h, _ in expired:
            del self.in_flight[h]
        return expired

    def is_done(self, my_height: int, my_tip: str, peer_statuses) -> bool:
        """True when we match the tallest known peer's height and tip."""
        if not peer_statuses:
            return False
        tallest = max(height for height, _tip in peer_statuses.values())
        return my_height == tallest and any(
            height == my_height and tip == my_tip
            for height, tip in peer_statuses.values()
        )
