# kwartel.node

The node layer: a simulated in-process network where three independent full
nodes exchange blocks and transactions over an in-memory message bus.

## Why gossip / broadcast?

Every node broadcasts newly mined blocks and newly submitted transactions to all
peers.  Gossip makes the network self-healing: a node that misses a message
because it was offline or partitioned can later ask its peers for what it missed.
There is no central server; each node is a peer.

## What do INV_BLOCK and GET_BLOCK solve?

Broadcasting every block in full is wasteful when many peers already have it.
The INV/GET handshake sends a compact inventory announcement (`INV_BLOCK`, just
the 32-byte hash) first.  A peer that does not have that block asks for it with
`GET_BLOCK`, and the holder replies with the full `BLOCK`.  After a partition
heals, this is how nodes discover and fetch the blocks they are missing.

## What is a partition?

A partition is a network split: some nodes can only talk to each other, not to
the rest.  During a partition, each side keeps mining, so the chain temporarily
forks.  Here it is simulated with `NetworkBus.partition()`.

## Why does longest-chain heal a partition?

When the partition heals, both sides exchange blocks.  Kwartel's fork choice is
the longest chain: the fork with the most blocks wins, and the shorter fork's
tip blocks are discarded (a reorg).  Because the choice depends only on the
blocks themselves (not on who saw what first), every node reaches the same
conclusion and the network converges.

## What does a node store locally?

Each `FullNode` owns its own SQLite `BlockStore` (blocks + tips), an in-memory
`Chain` (UTXO set, fork choice), a `Mempool` of pending transactions, and a
wallet keypair.  Nodes share no memory; they only exchange serialized messages
over the bus.

## Phase 2: TCP transport (`NetNode`)

`NetNode` runs the same gossip logic over real TCP sockets instead of the
in-memory bus. The shared message handling lives in `gossip.py`; `FullNode` (bus)
and `NetNode` (TCP) both call it and only differ in how messages are delivered.

### Memory-bus topics → wire topics

| Bus topic (Phase 1) | Wire topic id (Phase 2) | Meaning |
|---|---|---|
| `BLOCK` | 6 | canonical serialized block |
| `TX` | 7 | canonical serialized tx |
| `INV_BLOCK` | 8 | 32-byte block-hash announcement |
| `GET_BLOCK` | 9 | 32-byte block-hash request |
| *(new)* `GET_STATUS` | 10 | request peer's (height, tip_hash) |
| *(new)* `STATUS` | 11 | reply: `u64 LE height` + 32-byte tip hash |

### Why INV/GET instead of always pushing blocks?

Pushing every block to every peer is wasteful when most peers already have it.
`INV_BLOCK` is a compact 32-byte announcement; a peer that lacks the block asks
for it with `GET_BLOCK`. This is also how multi-hop propagation works: a node
that adds a block re-announces `INV_BLOCK`, so a peer two hops away can fetch it.

### Why an orphan buffer?

Blocks can arrive out of order (a node may get block N+2 before N+1, e.g. right
after a partition heals). The orphan buffer holds such blocks and re-tries them
once their parent arrives, after requesting the missing parent with `GET_BLOCK`.

### What is STATUS for?

On connect, the connector sends `GET_STATUS`; the responder replies `STATUS`
(height + tip). If the peer's tip is taller and unknown, the connector requests
it — this is the catch-up trigger after a partition heals.

### Why partitions are just dropped connections

There is no "partition" flag anymore. A partition is simply the set of peers we
are currently connected to; splitting the network means closing the cross-group
connections. Healing means reconnecting them, which re-triggers the status
exchange and sync.

## Phase 2: Peer discovery & initial block download

### Why peer gossip beats hardcoded seeds long-term

A hardcoded seed list is a single point of failure and a manual chore. With
gossip discovery, every node shares the addresses it has learned, so the network
bootstraps itself: a fresh node that knows only one address discovers the rest
organically (`GET_PEERS` / `PEERS`), and each node's address book is persisted
to `peers.json` so it remembers peers across restarts.

### "observed" vs "configured" vs "peer"

- **configured** — an address given explicitly at startup (`--peers`). Never
  evicted, never dropped, only failure-marked.
- **observed** — the address of a peer we actually completed a handshake with
  (from the handshake's `listen_port`). Highest confidence.
- **peer** — an address learned from another node's `PEERS` message. Trusted
  less, and the first to be evicted when the book is full.

### Why IBD is automated GET_BLOCK, not a trust shortcut

Initial block download is just a loop of the same `GET_BLOCK`/`BLOCK` messages
used everywhere else. A node that sees a taller peer requests its tip; the block
arrives, is validated by `chain.add_block` exactly like any other block, and the
orphan buffer fetches its ancestors one at a time. There is no "download mode"
that skips validation — a bad-PoW or otherwise invalid block is rejected during
IBD exactly as it would be at steady state.

### How orphan rescue and IBD compose

IBD starts the download at the *tip*; orphan rescue finishes it. The tip block's
parent is usually unknown, so it is parked in the orphan buffer and the parent is
requested, walking back to the common ancestor. Once the ancestor is reached,
the pending chain is re-applied in order via `chain.add_block`, and fork choice
picks the longest chain. So the `SyncPlanner` only ever asks for a tip; the
existing orphan mechanism does the rest.

### Eviction rationale

The address book is capped at 1000 entries. When full, the oldest `"peer"`
entry is evicted first, then the oldest `"observed"`; `"configured"` entries are
never evicted. Failure tracking (`mark_failed`) drops an entry after 5 failures,
so unreachable peers naturally age out of the book.


