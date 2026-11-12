"""In-memory message bus for the Kwartel simulated network."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Message:
    """A single message delivered to a node's mailbox."""

    topic: str
    payload: bytes
    sender: str


class Mailbox:
    """A node's view of the bus: send to peers and drain received messages."""

    def __init__(self, node_id: str, bus: "NetworkBus") -> None:
        self.node_id = node_id
        self._bus = bus
        self._inbox: list[Message] = []

    def send(self, topic: str, payload: bytes) -> None:
        """Queue a message from this node to all others."""
        self._bus.send(self.node_id, topic, payload)

    def drain(self) -> list[Message]:
        """Return and clear all messages currently queued for this node."""
        messages = self._inbox
        self._inbox = []
        return messages


class NetworkBus:
    """Synchronous in-memory pub/sub with explicit flush and partitioning."""

    def __init__(self) -> None:
        self._mailboxes: dict[str, Mailbox] = {}
        self._queue: list[tuple[str, str, bytes]] = []
        self._groups: list[frozenset[str]] | None = None

    def register(self, node_id: str) -> Mailbox:
        mailbox = Mailbox(node_id, self)
        self._mailboxes[node_id] = mailbox
        return mailbox

    def send(self, sender: str, topic: str, payload: bytes) -> None:
        self._queue.append((sender, topic, payload))

    def flush(self) -> None:
        """Deliver all queued sends to recipient inboxes, honouring partitions."""
        pending = self._queue
        self._queue = []
        for sender, topic, payload in pending:
            for node_id, mailbox in self._mailboxes.items():
                if node_id == sender:
                    continue
                if not self._can_reach(sender, node_id):
                    continue
                mailbox._inbox.append(Message(topic, payload, sender))

    def pending_count(self) -> int:
        return len(self._queue)

    def inbox_count(self) -> int:
        return sum(len(mb._inbox) for mb in self._mailboxes.values())

    def _group_of(self, node_id: str) -> frozenset[str] | None:
        if self._groups is None:
            return None
        for group in self._groups:
            if node_id in group:
                return group
        return None

    def _can_reach(self, a: str, b: str) -> bool:
        if self._groups is None:
            return True
        return self._group_of(a) == self._group_of(b)

    def partition(self, groups: list[set[str] | frozenset[str]]) -> None:
        """Restrict delivery to within each group of node ids."""
        self._groups = [frozenset(g) for g in groups]

    def heal(self) -> None:
        """Remove partitioning, restoring full connectivity."""
        self._groups = None
