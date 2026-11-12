# Project Kwartel (KWT) — Phase 2, Task 03: Peer Discovery & Initial Chain Sync

> **Model tier:** DeepSeek V4 Pro (sync state machines + async — edge cases hide here).
>
> **Cline instructions:** Read fully before coding. TDD per task. Append to
> `FINDINGS.md`. No git commits. Never log secret keys. No floats.
>
> **Standing rules unchanged:** transport ≠ trust (inbound peers/blocks/txs are
> hostile until validated), malformed input disconnects never crashes, validation
> imported not copied, every async test carries a timeout.

## Context

Phase 2 Tasks 01–02 accepted: TCP wire + handshake, gossip over sockets
(BLOCK/TX/INV_BLOCK/GET_BLOCK/GET_STATUS/STATUS), orphan rescue, partition +
heal, cluster test helper. Remaining gap: **peers are configured manually and a
new node cannot obtain the chain.** This task closes both:

1. **Peer discovery** — nodes exchange peer lists organically (gossip-based discovery).
2. **Initial block download (IBD)** — a brand-new node joins a live network and
   reaches the current tip without any manual intervention.

After this task, the demo scenario is: network running with N nodes and M
blocks → a completely fresh node learns one address, connects, and syncs to tip.

## Deliverables

### Files
- Extend `kwartel/net/framing.py`: `GET_PEERS = 12`, `PEERS = 13`
- Extend `kwartel/net/server.py` / `kwartel/net/peer.py`: peer address book persistence support (see Part B)
- `kwartel/node/discovery.py` — peer exchange + address book logic (pure functions where possible)
- Extend `kwartel/node/netnode.py` — discovery + IBD wiring
- `kwartel/node/sync.py` — initial block download state machine (pure-ish, testable)
- Extend `kwartel/node/cluster.py` — helpers for IBD tests
- Extend `kwartel/node/__main__.py` — Act 6: fresh node joins a running network
- Extend `kwartel/node/README.md`
- `tests/node/test_discovery.py`, `tests/node/test_sync.py`

### Part A: Peer exchange protocol

Wire message `PEERS` payload: `u16 LE count`, then count × (`u8 host_len` + host bytes + `u16 LE port`). Hosts are IP strings (v4 only for Phase 2). Cap count at 64.

- On **successful handshake completion** (both directions), each side sends `GET_PEERS`.
- On `GET_PEERS`: reply `PEERS` with up to 64 known addresses (from the address book, Part B — exclude the requester's own address and the requester itself).
- On `PEERS`: validate structure (bounded count, sane host lengths, port ≥ 1), then merge into the address book. Malformed = disconnect.
- **Periodic gossip:** every `DISCOVERY_INTERVAL = 30s` (config constant, overridable in tests), a node sends `GET_PEERS` to a random live peer. Background task; started in `NetNode.start()`, cancelled in `stop()`.

### Part B: Address book (in discovery.py)

`AddressBook` class (persisted to `peers.json` in the node's data dir):

- `add(host, port, source)` — dedup on (host, port); source ∈ {"configured", "peer", "observed"}; cap 1000 entries, evict oldest "peer"-sourced when full (configured entries never evicted).
- `get_batch(n, exclude)` — n random distinct entries excluding a set.
- `mark_failed(host, port)` — increment failure count; ≥ 5 failures → drop (configured entries never dropped, only marked).
- `all()`, `__len__`, persistence: `save(path)` / `load(path)` (JSON; tolerate corrupt file by starting empty — never crash on it).
- The node's own listen address is recorded with source "observed" by peers via handshake `listen_port` (already in the wire format from Task 01 — finally its purpose). When a handshake completes, add (remote_host, remote.listen_port, "observed") to the book.

### Part C: Initial block download (sync.py)

State machine — the joining node's logic, driven by STATUS/INV messages it
already receives plus one new behavior:

- `SyncPlanner`: given (my_height, my_tip, peer_statuses, blocks_in_flight) →
  decide next actions. Pure and unit-testable:
  - If some peer's height > my_height and we have fewer than `MAX_INFlight = 8`
    block requests outstanding → request that peer's tip hash chain via
    `GET_BLOCK` for the tip (orphan rescue already walks ancestors via
    GET_BLOCK — verify this composes; if ancestor fetching is too slow one
    block at a time, ADD `GET_BLOCKS` topic: `u32 LE count` + hashes, reply
    with consecutive `BLOCK` messages — decide based on what the orphan
    mechanism actually does, document the choice).
  - Track in-flight requests with timeouts (30s) — re-request or try another peer.
- IBD completion: my tip matches a peer's tip AND height equal → sync done,
  emit log line. Multiple taller peers: pick the tallest (chain identity already
  enforced via genesis hash in handshake).
- **Safety:** every block received during IBD passes the same `chain.add_block`
  validation as always. IBD is not a trust shortcut — it's just automated GET_BLOCK.

### Part D: NetNode wiring

- On handshake completion (either direction): GET_PEERS + GET_STATUS exchange.
- On `PEERS`: merge into address book; optionally connect out to learned peers
  until `max_peers` reached (connect to at most 2 new peers per batch to avoid
  storms; never connect to self/already-connected).
- On STATUS showing a taller peer: hand to SyncPlanner; issue requests.
- On periodic discovery tick: GET_PEERS to one random peer.
- Restart persistence test: address book survives restart (peers.json roundtrip).

### Part E: Tests

1. `test_peer_exchange_two_nodes`: A↔B handshake → both books contain each other (source "observed").
2. `test_peers_message_validation`: malformed PEERS payload (bad count, oversized host, zero port) → peer disconnected, node alive.
3. `test_three_node_discovery`: A↔B, A↔C connected; B learns C's address from A (source "peer"); B can connect to C using only book data.
4. `test_address_book_persistence`: book → save → new book → load → same entries; corrupt JSON → empty book, no crash.
5. `test_eviction`: fill book to cap with peer-sourced entries → oldest evicted; configured entries never evicted.
6. `test_ibd_fresh_node`: network of 3 nodes mines 10 blocks (with a few txs), fresh node D starts with only A's address configured → D reaches tip (same height, same tip hash, balances correct) within timeout. **This is the gate test for the whole task.**
7. `test_ibd_picks_tallest`: D sees two peers with different heights → syncs to tallest.
8. `test_sync_timeout_retry`: peer that dies mid-sync → D retries via another peer (simulate: stop one node after GET_BLOCK sent).
9. `test_no_ibd_shortcut`: during IBD, send D an INVALID block (bad PoW) → rejected, D still converges via honest chain.

### Part F: Demo (extend `kwartel/node/__main__.py`)

Act 6 — "cold join": after the existing five acts (network at height 7), boot a
brand-new node `node3` knowing only node1's address, wait for IBD, print its
height/tip/balances matching the network. End line:
`PHASE 2 TASK 03 COMPLETE: fresh node cold-joined and synced to tip.`

### Part G: README additions

Why peer gossip beats hardcoded seeds long-term; what "observed" vs "configured" means; why IBD is automated GET_BLOCK rather than a trust shortcut; eviction policy rationale; how orphan rescue and IBD compose.

## Acceptance criteria

1. `pytest tests/ -v` all green (174 + new; nothing broken)
2. Demo Act 6 passes — cold join works
3. No validation duplicated; all state machines unit-testable without sockets where possible
4. Address book survives restart; corrupt peers.json tolerated
5. No test hangs; no busy-wait loops (sleep-poll with timeouts is fine)
