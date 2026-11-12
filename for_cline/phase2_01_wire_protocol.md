# Project Kwartel (KWT) — Phase 2, Task 01: TCP Wire Protocol & Handshake

> **Model tier:** Kimi K2.7 Code (integration/plumbing). Consensus logic exists;
> this task must REUSE it. If copying validation code, STOP — import it.
>
> **Cline instructions:** Read fully before coding. TDD per task. Append to
> `FINDINGS.md`. No git commits. Never log secret keys. No floats.
>
> **CRITICAL RULE — transport ≠ trust:** any peer can send any bytes. EVERY
> inbound message must be size-limited, timeout-bound, and validated exactly
> like locally-produced data. A malformed message = disconnect that peer, never
> crash the node. Never parse untrusted input without a length cap.

## Context

Phase 1 gave us a complete chain core + simulated in-memory bus (deterministic,
no sockets). Phase 2 replaces the bus with **real TCP on localhost**. Same node
logic (`FullNode`), same validation, new transport. Everything runs on one
machine: 3+ node processes binding distinct `127.0.0.1` ports.

This task delivers ONLY: framing, handshake, peer lifecycle, and a message
relay. Block/tx gossip over TCP comes in Task 02 after this layer is proven.

## Deliverables

### Files
- `kwartel/net/__init__.py`
- `kwartel/net/framing.py` — length-prefixed framing (read/write full messages)
- `kwartel/net/handshake.py` — magic + version exchange
- `kwartel/net/peer.py` — Peer connection wrapper
- `kwartel/net/server.py` — asyncio server accepting peers
- `tests/net/test_framing.py`, `test_handshake.py`, `test_server.py`

### Part A: Framing (framing.py)

Binary, length-prefixed, canonical:

```
[u32 LE payload_len][u16 LE topic_id][payload]
```

- `MAX_PAYLOAD = 8 MiB` (blocks are small in Phase 2; cap anyway). Reading a
  length > cap or a connection that sends garbage = protocol error → close.
- `async read_message(reader) -> Message | None` (None = clean EOF) and
  `async write_message(writer, topic, payload)`. Use `asyncio.open_connection`
  / `start_server` primitives. Enforce a read timeout (e.g. 30s idle) via
  `asyncio.wait_for` — dead peers must not hold resources.
- Topic registry: explicit `TOPICS = {"HANDSHAKE": 1, "HANDSHAKE_ACK": 2, ...}`
  with ids fixed in one dict — no magic numbers scattered in code. Unknown
  topic = protocol error.
- Tests: roundtrip all topics, oversized length rejected, truncated payload
  rejected, garbage bytes rejected, EOF → None.

### Part B: Handshake (handshake.py)

Before any other message flows:

```
1. Connector sends HANDSHAKE: {magic, version, node_id (32B), genesis_hash (32B), listen_port}
2. Responder validates and replies HANDSHAKE_ACK: {magic, version, node_id, genesis_hash, listen_port}
3. Both sides: if magic/genesis mismatch → disconnect. If same node_id seen
   twice → disconnect (self-connect guard).
```

- `PROTOCOL_MAGIC = 0x4B575431` ("KWT1") and `PROTOCOL_VERSION = 1`. Genesis
  hash comes from the pinned genesis — peers on different chains must refuse to
  talk. Same-version policy for Phase 2: exact match required (simple; relax
  later with negotiation).
- Serialize handshake payloads canonically (reuse length-prefixed style).
- Tests: happy path both directions, magic mismatch → disconnect, genesis
  mismatch → disconnect, self-connect (same node_id) → disconnect.

### Part C: Peer + Server (peer.py, server.py)

- `Peer`: wraps reader/writer for one connection. Fields: node_id (learned from
  handshake), addr, last_seen. Methods: `send(topic, payload)`,
  `close()`. Track `alive` flag; write failures → mark dead, close.
- `Server`: asyncio TCP server on configured host:port. On accept: frame-read
  the handshake, validate, register the peer in a `PeerBook`. Exposes
  `broadcast(topic, payload)` (all live peers), `send_to(node_id, ...)`,
  `peer_count()`. Disconnected peers are removed from the book.
- **PeerBook** (inside server.py): `add`, `remove`, `get(node_id)`, `all()`.
  No peer discovery protocol yet (Task 03) — peers are configured manually.
- Config: `kwartel/net/config.py` — dataclass `NetConfig(host="127.0.0.1", port, max_peers=16, handshake_timeout=10, idle_timeout=30)`. Node binaries take `--port` and `--peers host:port,host:port`.
- Tests (use two real in-process servers on ephemeral 127.0.0.1 ports): handshake
  success both ways, broadcast reaches all peers, dead-peer cleanup, oversized
  message → disconnect, handshake timeout → disconnect.

### Part D: Integration test (test_server.py::test_three_nodes_exchange)

Three servers on ephemeral ports, A→B, B→C connections established with
handshakes. A broadcasts a test topic message; assert B and C both receive it
(C via B relay? NO — this task has no relay; connect C→B directly so the mesh
is A↔B↔C; broadcast at B reaches both). This test is the gate for Task 02.

## Acceptance criteria

1. `pytest tests/ -v` all green (143 existing + new; node tests untouched)
2. No global mutable state; server/peers cleanly startable + stoppable in tests
3. Every async test has a timeout (pytest-asyncio or explicit wait_for) — no test can hang CI
4. README (kwartel/net/README.md): explain length-prefix framing (vs delimiter), why magic+genesis in handshake, why inbound data is treated as hostile
5. Demo: `python -m kwartel.net` boots two nodes on ports 9371/9372, performs handshake, exchanges a ping/pong message, prints results (output → FINDINGS.md)
