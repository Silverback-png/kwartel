# Project Kwartel (KWT) — Phase 2, Task 02: Block & Tx Gossip over TCP

> **Model tier:** DeepSeek V4 Pro (networking + state machine interaction —
> reorgs over async sockets have more edge cases than they appear to).
>
> **Cline instructions:** Read fully before coding. TDD per task. Append to
> `FINDINGS.md`. No git commits. Never log secret keys. No floats.
>
> **Standing rules that still apply:** transport ≠ trust — every inbound block/tx
> is deserialized then passed through the SAME validation as local data. A
> rejected message = drop it (and optionally disconnect on protocol garbage),
> never crash. Validation logic is imported, never copied.

## Context

Phase 2 Task 01 gave us the wire: framing, handshake, peer book, broadcast.
Phase 1 gave us FullNode logic over a deterministic memory bus. This task
**merges them**: real `FullNode`s whose gossip now travels over real TCP
sockets. The end state: the Phase 1 five-act demo (funding → payment →
partition → heal) re-run over sockets, with partitions enforced by dropping
connections, not bus flags.

Design principle: the node logic from `kwartel/node/` stays the source of
truth. We adapt the transport *under* it. Where the memory-bus version had
`bus.flush()`, the socket version has background reader tasks; the node's
message-handling functions must be callable from both (extract/reuse, don't
fork the logic).

## Deliverables

### Files
- `kwartel/node/netnode.py` — `NetNode`: FullNode over TCP (adapter, not a rewrite)
- `kwartel/node/cluster.py` — test/demo helper: spin up N NetNodes on ephemeral ports, connect mesh, teardown
- `kwartel/node/__main__.py` — extend demo: five acts over TCP
- `tests/node/test_gossip.py`, `tests/node/test_partition_tcp.py`
- Extend `kwartel/node/README.md`

### Part A: Wire topics (extend framing TOPICS)

Existing topics stay. ADD (next free ids, documented in one place):
- `BLOCK` — canonical serialized block (serialize_block)
- `TX` — canonical serialized tx (serialize_tx include_signatures=True)
- `INV_BLOCK` — 32-byte block hash announcement
- `GET_BLOCK` — 32-byte block hash request
- `GET_STATUS` — request peer's (height, tip_hash)
- `STATUS` — reply: `u64 LE height` + 32-byte tip hash

(The BUS in kwartel/node/network.py used the same topic names — reuse names,
new ids live in the wire TOPICS dict.)

### Part B: NetNode (netnode.py)

```python
class NetNode:
    def __init__(self, node_id_str: str, data_dir: Path, listen_port: int | None = None)
    # internally: Server (from kwartel.net) + Chain + Mempool + wallet-free
    async def start() / async def stop()
    async def connect(host, port)          # outbound, handshake, then GET_STATUS
    def submit_tx(tx) -> bool              # accept locally, broadcast TX
    # background: reader pump — for each received message:
```

Message handling (reuse Phase 1 semantics):
- `BLOCK`: deserialize → `chain.add_block` → on success: remove block's txs
  from mempool, broadcast `INV_BLOCK`. On "parent not found": store as orphan +
  send `GET_BLOCK` for parent (reuse the pending-map pattern from Task 05).
- `TX`: deserialize → `mempool.accept(tx, chain.utxo_set())` — accept silently,
  no rebroadcast (originator gossips once; storm prevention).
- `INV_BLOCK`: if block unknown → send `GET_BLOCK`.
- `GET_BLOCK`: reply with `BLOCK` if we have it.
- `GET_STATUS`: reply `STATUS` (height + tip). On connect completion, exchange
  statuses; if peer's tip is taller and unknown → send `GET_BLOCK` for it.
- Every handler wraps validation failures: drop + log, never crash. Malformed
  deserialize = disconnect that peer (protocol garbage).

### Part C: Cluster (cluster.py)

- `Cluster`: `async add_node(port=None) -> NetNode` (ephemeral ports via port 0,
  actual port from server), `async connect_mesh()` (full mesh), `async connect_linear()`
  (A→B→C only — needed to test multi-hop INV/GET), `async stop_all()`.
- `async partition(groups)`: close all Server-side connections between groups
  (implement as: for each peer in book whose node_id is in a foreign group →
  `peer.close()` + book.remove). `heal()`: re-run the original connect topology.
- Expose `wait_until_converged(timeout) -> bool`: poll all nodes until every
  height/tip_hash matches the max-height node's tip (bounded loop with small
  asyncio.sleep — polling is FINE for tests; no busy-wait).

### Part D: Tests (the gate)

1. `test_two_nodes_sync_block`: node A mines (reuse miner helper from Task 05
   adapted to NetNode), A broadcasts BLOCK → B's height == A's height, same tip.
2. `test_tx_propagates_and_gets_mined`: A submits tx (funded via premine from
   genesis dev key — mine a funding block first), tx reaches B's mempool; B
   mines a block including it; block reaches A; both show same balance.
3. `test_orphan_rescue`: A mines block N+1 and N+2 quickly (before B hears of
   N+1 — serialize: don't flush until both mined), then B receives N+2 first →
   orphan handling → GET_BLOCK → B ends with both blocks, correct tip.
4. `test_partition_and_heal_tcp`: 3 nodes fully meshed, everyone synced. Split
   {A} vs {B,C} via real connection drops; A mines 2, B/C mine 3; heal (reconnect);
   `wait_until_converged` → all three on B/C's tip; A's balances reflect fork reality.
5. `test_linear_topology_multihop`: A→B→C linear; A mines; C (2 hops away) must
   still converge via INV/GET relaying (B rebroadcasts after adding the block).
6. `test_hostile_block_dropped`: send garbage bytes as BLOCK topic → node stays
   alive, peer may be dropped, node still mines/validates afterwards.
7. `test_status_exchange`: fresh node connects → learns height/tip of peer.

Every test: explicit timeout wrapper (existing pattern), clean teardown via Cluster.stop_all().

### Part E: Demo (extend `kwartel/node/__main__.py`)

Re-run the five acts over TCP:
1. Boot 3 NetNodes (fresh data dirs under `data/netdemo/`), full mesh, wait converged
2. Each mines a funding block → converge
3. Alice (wallet from Phase 1 wallet.py, pointed at NetNode A) pays Bob 30 SHAP → propagate → someone mines → converge, Bob consistent on all nodes
4. Partition {A} / {B,C} (real disconnects) → A mines 2, B/C mine 3 → competing tips
5. Heal → wait_until_converged → all on B/C tip, "PHASE 2 TASK 02 COMPLETE: 3 TCP nodes converged after partition + reorg."
Output → FINDINGS.md.

### Part F: README additions

Map memory-bus topics → wire topics; explain INV/GET vs pushing blocks; why
orphan buffer exists; what STATUS exchange is for; why partitions are just
dropped connections.

## Acceptance criteria

1. `pytest tests/ -v` all green (167 + new; Phase 1 node/bus tests untouched)
2. Demo ends with the completion line, all nodes same tip
3. No validation duplicated — kwartel.net does transport only, kwartel.blockchain does truth only
4. Every handler survives malformed input (garbage bytes test proves it)
5. Multi-hop test proves INV/GET relaying works beyond direct peers
