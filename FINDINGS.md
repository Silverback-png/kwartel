# Phase 1 Task 01 — Crypto Module Findings

## Environment note

The workspace did not have a system Python 3.11 installation. I installed the
official Python 3.11.9 embedded distribution at `C:\Users\TTEMPESTT\Python311`,
enabled `import site` in `python311._pth`, installed pip via `get-pip.py`, and
then created the project virtualenv with `python -m virtualenv` (the embedded
distribution does not include the `venv` stdlib module). The spec's suggested
`python -m venv .venv` command could not be used verbatim; this is recorded as a
deviation.

## Deviation from spec

The spec requested `nacl.bindings.crypto_sign_verify_detached` for signature
verification. That function is not exported by PyNaCl 1.6.2; only
`crypto_sign` and `crypto_sign_open` are available in the low-level bindings. I
implemented detached verification by concatenating `signature + message` and
calling `crypto_sign_open`, which is the libsodium-equivalent operation. The
high-level `nacl.signing` API also supports detached verification, but I stayed
with the low-level bindings as requested.

## Demo output (`python -m kwartel.crypto`)

```
secret (hex): [redacted per new standing rule: never print or write secret keys]
public (hex): bde7d2905b01906409d0ceedc9f77c7af159553f48adb643741fa5112deded82
address:      KWT12SdtBxA4MFq5vG6CmMYR7zMTMALvrwFgRt2jUb9Nqo3YM5HByV
message:      b'Kwartel Phase 1 Task 01 demo'
signature:    21603f6751db5a985009622625d765e819bc5bb7bca7ba3bf9758879e4d90c5c2231699e6395e3538133cd4cf9e257ae601fe1188c2373a14b3441c84fa57506
verified:     True
```

## Test results

`pytest tests/crypto -v` passes all 22 tests.

## Files created

- `kwartel/crypto/__init__.py`
- `kwartel/crypto/keys.py`
- `kwartel/crypto/base58.py`
- `kwartel/crypto/__main__.py`
- `kwartel/crypto/README.md`
- `tests/crypto/test_keys.py`
- `tests/crypto/test_base58.py`
- `requirements.txt`
- `FINDINGS.md`

---

# Phase 1 Task 02 — UTXO Transaction Model Findings

## Standing rule applied

No secret keys are printed in the Task 02 demo or in this section. Only
addresses and public-key-derived identifiers are shown.

## Demo output (`python -m kwartel.transaction`)

```
Alice address: KWT1Ywi4i74GxHNAnuNeGjWaQNiwojmVJFcgRs9RdWFw7k5SRHx1Z
Bob address:   KWT1tVND4jjVZU7Sb6msotAUQairXnj1USa39eVFH222juxNK8cWb

Initial UTXO set size: 1
Alice's initial balance: 100 KWT (10000000000 kwarts)
Bob's initial balance:   0 KWT (0 kwarts)

Transaction txid: 513dccfa383dd9b8bc3ea35325446e8940ce7145a51796acb9fddbdac908b1bc
Fee:              0 KWT (0 kwarts)
Violations:       []

UTXO set size after apply: 2
Alice's balance: 50 KWT (5000000000 kwarts)
Bob's balance:   50 KWT (5000000000 kwarts)

Double-spend rejected: transaction validation failed:
outpoint not found: Outpoint(txid='0000000000000000000000000000000000000000000000000000000000000000', index=0)
outputs exceed inputs (conservation violation)
```

## Design notes

- All monetary values are stored as integer kwarts. The demo prints KWT for
  readability using integer division only.
- `validate_tx` returns a list of violations and never raises, even on
  pathological input such as negative output values.
- The txid is computed from a canonical serialization that excludes signatures,
  matching Bitcoin's approach and avoiding circular signing dependencies.
- Double-spend protection exists in two places: the mempool rejects conflicting
  inputs, and the UTXO set removes spent outputs atomically after validation.

## Test results

`pytest tests/ -v` passes all 63 tests (22 crypto + 41 transaction).

## Files created / modified

- `kwartel/transaction/__init__.py`
- `kwartel/transaction/model.py`
- `kwartel/transaction/validation.py`
- `kwartel/transaction/utxo_set.py`
- `kwartel/transaction/mempool.py`
- `kwartel/transaction/__main__.py`
- `kwartel/transaction/README.md`
- `tests/transaction/test_model.py`
- `tests/transaction/test_validation.py`
- `tests/transaction/test_utxo_set.py`
- `tests/transaction/test_mempool.py`


## Note on the new "no secret keys" standing rule

The standing rule introduced in Task 02 was applied retroactively to the Task 01
crypto demo: `kwartel/crypto/__main__.py` no longer prints the secret seed, and
the historical secret in the Task 01 demo output above has been redacted.



---

# Phase 1 Task 03 — Blocks & Merkle Trees Findings

## Standing rule applied

No secret keys are printed in the Task 03 demo or in this section. Only public
addresses and transaction/block identifiers are shown.

## Demo output (`python -m kwartel.blockchain`)

```
Addresses (no secret keys shown):
  Dev:    KWT1CR37vE5vUeGDR3KZVDL78gvvUHdrquNzVH9AoSiFk4YqUYUnd
  Bob:    KWT1aN9FAfupbEwdwGEPtV7imbdoaqHoad5vpAEUGv6AKGSsMLajz
  Charlie: KWT1ySaSJ67fjQtPgtZ4EtiDCV6SmrhsNfuqvo9paA5KJxvdGCDqz
  Dave:   KWT1JhSoFz2ygop7U4oCkvywJzPSXoESAS5MmC5VT4yjZxi1m1a9k

Genesis block hash: 0066ff4f7f12ef0d37e739b8d6ae774a42620dcd2cea20461e7eda131ed1de02
Genesis nonce:      61
Genesis leading zero bits: 9

Tx1 txid: 4b65825de95d43213315404cb387e5aaab15c6393aabfb26dbc8e94e797fe994 violations: []
Tx2 txid: 70b7b7dce226c74ee9c028f8a8f8e1cf1dfb24a3c93706e902922d82a972fe7f violations: []
Tx3 txid: 1a89cec930894e16bf4a08795241050882e6b0bc84fbc82df55ffaeec5fc14ec violations: []

Merkle root of 3 txs: d829d041038b6b623dada25a5b0301ad0c020b379e86de995c0c0a556aa4dd9e

Second block hash: 0085c77f498e8dd6187f93aa79a976e57e41c535f134530fecb602eaa0f05f82
Second block merkle root: d829d041038b6b623dada25a5b0301ad0c020b379e86de995c0c0a556aa4dd9e
Second block nonce: 91
Mining time: 0.0005s
Leading zero bits: 8
Meets difficulty: True

Tamper demo:
  Original merkle root: d829d041038b6b623dada25a5b0301ad0c020b379e86de995c0c0a556aa4dd9e
  Tampered merkle root: 8a0544426880f0e4fa0dcd72aaae18e92e36cb064e312bdf70a82f5e5f8e92e3
  Merkle root changed:  True
  Tampered block hash:  ba8ee35a16783f9b4cbf773c7a326a1ba0067fb7361c622475f4cf6b1464a8fc
  Leading zero bits of tampered block: 0
  Tampered block meets difficulty: False
```

## Design notes

- **Merkle odd-node duplication:** Kwartel duplicates the last node on odd levels
  (Bitcoin-style). This is simple but has a known structural weakness,
  CVE-2012-2459, where duplicate leaves can sometimes be rearranged without
  changing the root. We mitigate this by validating the actual transactions
  inside a block, not by trusting the Merkle root alone.
- **Single-leaf rule:** A single transaction is duplicated and hashed once
  (`sha256(leaf || leaf)`), so the root is never equal to the raw txid.
- **Difficulty in bits:** `difficulty` is the number of leading zero BITS that
  `sha256(serialize_header)` must have. Difficulty 8 gives roughly a 1/256
  chance per nonce and mines in milliseconds on a CPU.
- **Tamper cascade:** The header commits to `prev_block_hash` and `merkle_root`,
  so changing any transaction changes the Merkle root, which changes the block
  hash, which changes the next block's `prev_block_hash`, invalidating every
  later header.
- **Pinned genesis:** The canonical genesis block has a fixed timestamp,
  difficulty, payout public key, and nonce. Its hash is hardcoded in the tests
  so every node starts from the same chain tip.

## Canonical genesis block

```
GENESIS_NONCE = 244
GENESIS_HASH  = 00672dafecdc4b0708dddcbb82337a713f209858083d129ac0e3d5349054694f
```

(The demo uses a freshly generated spendable keypair, so its demo genesis hash
is different from the pinned canonical hash above.)

## Test results

`pytest tests/ -v` passes all 98 tests (22 crypto + 41 transaction + 35 blockchain).

## Files created

- `kwartel/blockchain/__init__.py`
- `kwartel/blockchain/merkle.py`
- `kwartel/blockchain/block.py`
- `kwartel/blockchain/genesis.py`
- `kwartel/blockchain/__main__.py`
- `kwartel/blockchain/README.md`
- `tests/blockchain/__init__.py`
- `tests/blockchain/test_merkle.py`
- `tests/blockchain/test_block.py`
- `tests/blockchain/test_genesis.py`

---

# Phase 1 Task 04 — Blockchain, Validation & Persistence Findings

## Standing rule applied

No secret keys are printed in the Task 04 demo or in this section. Only public
addresses and block/tx identifiers are shown.

## Demo output (`python -m kwartel.blockchain`, chain section)

```
==============================================================
Chain demo (persistence + fork choice)
  Miner: KWT12Ggz237LaM3g9m5nDaoMj2rc47jRAx2T3hayQqxLYZA9YUJLFJ
  Alice: KWT1tvxDsUJP64GZ3rAKYmmvmr7GUAKc9tbBfWVujmeeJTP4TXyXn
  Genesis: height 0 hash 00672dafecdc4b07...

  block 1: add=[] height=1 tip=00bb029e33b7ccae... miner=5000000000 alice=0
  block 2: add=[] height=2 tip=00c910ae24f81b02... miner=5000000000 alice=5000000000
  block 3: add=[] height=3 tip=004cf30e488354b5... miner=5000000000 alice=10000000000
  block 4: add=[] height=4 tip=00e24cff9eadde5c... miner=5000000000 alice=15000000000

After 5-block fork overtakes:
  height=5 tip=00d33293c647fd98...
  old miner balance: 0
  alice balance:     0
  fork miner balance: 25000000000

Reopened from disk (fresh Chain object):
  height=5 tip=00d33293c647fd98...
  fork miner balance: 25000000000
  alice balance:      0
```

(Addresses and hashes vary per run because the demo generates fresh keys.)

## Design notes

- **State is derived, not stored.** The UTXO set at the tip is rebuilt by
  replaying the block log from genesis; SQLite stores only blocks.
- **Coinbase outpoint namespacing.** Coinbase txids can collide across blocks,
  so coinbase outputs are keyed in the UTXO set by `block_hash || txid`. This is
  the spec's "track by (block_hash, txid, index)" decision, implemented without
  touching the Task 02 dataclasses.
- **Coinbase maturity.** `COINBASE_MATURITY = 1`; a coinbase output cannot be
  spent until one block after it is mined.
- **First tx must be coinbase.** Gives validators one fixed place to check
  `value == BLOCK_REWARD + total fees`.
- **Fork choice.** Longest chain wins; a longer fork triggers a reorg that
  replays the new chain and rebuilds the UTXO set.

## Test results

`pytest tests/ -v` passes all 128 tests (22 crypto + 41 transaction + 65 blockchain).

## Files created / modified

- `kwartel/blockchain/coinbase.py` (new)
- `kwartel/blockchain/persistence.py` (new)
- `kwartel/blockchain/chain.py` (new)
- `kwartel/blockchain/__main__.py` (extended with chain + reorg + restart demo)
- `kwartel/blockchain/README.md` (extended)
- `kwartel/transaction/utxo_set.py` (added `UTXOSet.copy()` helper)
- `.gitignore` (new; ignores `data/`)
- `tests/blockchain/test_coinbase.py` (new)
- `tests/blockchain/test_persistence.py` (new)
- `tests/blockchain/test_chain.py` (new)

---

# Phase 1 Task 05 — Three-Node Network Demo Findings

## Standing rule applied

No secret keys are printed in the Task 05 demo or in this section. Only node
heights, block-hash prefixes, and balances are shown.

## Demo output (`python -m kwartel.node`)

```
PHASE 1 FINALE - three-node network demo

Act 1: boot
  node A: height=0 tip=00672dafecdc4b07...
  node B: height=0 tip=00672dafecdc4b07...
  node C: height=0 tip=00672dafecdc4b07...

Act 2: funding (one block per node)
  node A: height=3 tip=003370c4fea30358...
  node B: height=3 tip=003370c4fea30358...
  node C: height=3 tip=003370c4fea30358...
  converged: True

Act 3: Alice pays Bob 30 KWT
  node A: height=4 bob=30 KWT
  node B: height=4 bob=30 KWT
  node C: height=4 bob=30 KWT
  Bob balance consistent: True

Act 4: partition A | B,C
  node A: height=6 tip=0070d56b83316049...
  node B: height=7 tip=007f96746669767c...
  node C: height=7 tip=007f96746669767c...
  competing tips (A != B): True

Act 5: heal and converge
  node A: height=7 tip=007f96746669767c...
  node B: height=7 tip=007f96746669767c...
  node C: height=7 tip=007f96746669767c...
  all converged: True
  Bob balance: 30 KWT (consistent: True)

PHASE 1 COMPLETE: 3 nodes converged after partition + reorg.
```

(Tip hashes vary per run because nodes generate fresh keys.)

## Design notes

- **Gossip via an in-memory bus.** Nodes exchange only four message types —
  `BLOCK`, `TX`, `INV_BLOCK`, `GET_BLOCK` — with canonical serialized payloads.
  Delivery is fully deterministic: `bus.flush()` drives everything, no threads
  and no sleeps.
- **INV/GET handshake.** A node announces a compact inventory hash first; peers
  that lack the block request it with `GET_BLOCK`. This is how nodes recover
  blocks they missed during a partition.
- **Orphan handling.** A block whose parent is unknown is held in a pending map
  and its parent is requested; pending blocks are retried after each successful
  add. This makes the heal/reorg sync robust.
- **No validation duplicated.** The node layer only imports validation from
  `kwartel.blockchain` and `kwartel.transaction`; `chain.add_block` is the single
  source of truth.

## Test results

`pytest tests/ -v` passes all 143 tests (22 crypto + 41 transaction + 65 blockchain + 15 node).

## Files created / modified

- `kwartel/node/__init__.py` (new)
- `kwartel/node/network.py` (new)
- `kwartel/node/node.py` (new)
- `kwartel/node/miner.py` (new)
- `kwartel/node/wallet.py` (new)
- `kwartel/node/__main__.py` (new)
- `kwartel/node/README.md` (new)
- `kwartel/transaction/utxo_set.py` (added `UTXOSet.items()` helper)
- `tests/node/__init__.py` (new)
- `tests/node/test_bus.py` (new)
- `tests/node/test_node.py` (new)
- `tests/node/test_mining_sync.py` (new)
- `tests/node/test_partition.py` (new)

---

# Phase 2 Task 01 — TCP Wire Protocol & Handshake Findings

## Standing rule applied

No secret keys are printed in the demo or this section. Node identifiers are
random 32-byte values (`os.urandom(32)`), not key material, and the genesis hash
is the public pinned constant.

## Demo output (`python -m kwartel.net`)

```
PHASE 2 TASK 01 - TCP wire protocol + handshake demo

  node A listening on 127.0.0.1:9371
  node B listening on 127.0.0.1:9372

Act 1: A connects to B, handshake
  A learned B's node_id: 90afc397b47faebdf7c55328295362fc5ec05646d645ca468ab657c2f13c8539
  A peer_count=1, B peer_count=1

Act 2: A pings B, B replies pong
  B received PING: hello from A
  A received PONG: hello from B

PHASE 2 TASK 01 COMPLETE: handshake + ping/pong over TCP.
```

(node_id values vary per run because each boot generates fresh random bytes.)

## Design notes

- **Length-prefixed framing** (`framing.py`): every message is
  `[u32 LE payload_len][u16 LE topic_id][payload]`, with `MAX_PAYLOAD = 8 MiB`
  and a single `TOPICS` registry (`HANDSHAKE`, `HANDSHAKE_ACK`, `PING`, `PONG`,
  `DATA`) so topic ids live in exactly one dict. Reads are individually
  `asyncio.wait_for`-bounded so a dead peer cannot hold a read-loop task.
- **Handshake** (`handshake.py`): `PROTOCOL_MAGIC = 0x4B575431` ("KWT1"),
  `PROTOCOL_VERSION = 1`, exact same-version policy. Both directions exchange
  `{magic, version, node_id, genesis_hash, listen_port}`; any magic/version/
  genesis mismatch or a self-connect (`node_id == ours`) disconnects the peer.
- **Peer + server** (`peer.py`, `server.py`): `Peer` tracks `alive`/`last_seen`
  and closes on write failure. `Server` accepts peers (handshake-as-responder),
  connects out (handshake-as-connector), and exposes `broadcast`, `send_to`,
  `peer_count`, and `receive` over a `PeerBook`. Inbound data is treated as
  hostile: any `ProtocolError`/`HandshakeError`/`TimeoutError`/EOF tears down
  only that connection, never the node.
- **No new test dependency.** Async tests use the stdlib
  `asyncio.run(asyncio.wait_for(body(), timeout=15))` pattern (the spec permits
  "pytest-asyncio OR explicit wait_for"), so no `pytest-asyncio` install or
  config file was needed against the very new pytest 9.1.1.

## Test results

`pytest tests/ -q` passes all 167 tests (143 existing + 24 new: 8 framing,
8 handshake, 8 server). `tests/node/*` were not modified.

## Files created

- `kwartel/net/__init__.py`
- `kwartel/net/framing.py`
- `kwartel/net/handshake.py`
- `kwartel/net/peer.py`
- `kwartel/net/server.py`
- `kwartel/net/config.py`
- `kwartel/net/__main__.py`
- `kwartel/net/README.md`
- `tests/net/__init__.py`
- `tests/net/test_framing.py`
- `tests/net/test_handshake.py`
- `tests/net/test_server.py`

---

# Phase 2 Task 02 — Block & Tx Gossip over TCP Findings

## Standing rule applied

No secret keys are printed in the demo or this section. Only node heights,
block-hash prefixes, and balances are shown.

## Demo output (`python -m kwartel.node`)

```
PHASE 2 TASK 02 - three-node TCP gossip demo

Act 1: boot (full mesh)
  node node0: height=0 tip=00672dafecdc4b07...
  node node1: height=0 tip=00672dafecdc4b07...
  node node2: height=0 tip=00672dafecdc4b07...
  converged: True

Act 2: funding (one block per node)
  node node0: height=3 tip=00c28584b418a240...
  node node1: height=3 tip=00c28584b418a240...
  node node2: height=3 tip=00c28584b418a240...
  converged: True

Act 3: Alice pays Bob 30 SHAP
  node node0: height=4 bob=30 SHAP
  node node1: height=4 bob=30 SHAP
  node node2: height=4 bob=30 SHAP
  Bob balance consistent: True

Act 4: partition A | B,C
  node node0: height=6 tip=0089fdc02510819f...
  node node1: height=7 tip=0037df838d9d96be...
  node node2: height=7 tip=0037df838d9d96be...
  competing tips (A != B): True

Act 5: heal and converge
  node node0: height=7 tip=0037df838d9d96be...
  node node1: height=7 tip=0037df838d9d96be...
  node node2: height=7 tip=0037df838d9d96be...
  all converged: True
  Bob balance: 30 SHAP (consistent: True)

PHASE 2 TASK 02 COMPLETE: 3 TCP nodes converged after partition + reorg.
```

(Tip hashes vary per run because each boot generates fresh keys.)

## Design notes

- **Shared message handling (no fork).** The Phase 1 `FullNode` dispatch/orphan
  logic was extracted into `kwartel/node/gossip.py` as a pure, sync,
  transport-agnostic `handle_message(...)` that returns the outbound messages to
  send. `FullNode` (bus) and `NetNode` (TCP) both call it; each delivers the
  results over its own transport. Validation is still imported from
  `kwartel.blockchain`/`kwartel.transaction` (`chain.add_block`, `mempool.accept`).
- **Miner reuse.** `build_and_add_block(chain, mempool, pubkey)` was extracted
  into `miner.py`; `mine_once` (bus) and `NetNode.mine` (TCP) share it.
- **NetNode adapter.** `NetNode` wraps `Server` (from `kwartel.net`) + `Chain` +
  `Mempool`, with background reader/writer tasks. `submit_tx` stays sync and
  enqueues its broadcast; the writer loop delivers it. `node_id` (32 bytes) is
  `sha256(node_id_str)`, feeding the handshake.
- **Gossip routing.** `BLOCK`/`TX`/`INV_BLOCK`/`GET_BLOCK` are broadcast (mirrors
  the bus's send-to-all). `GET_STATUS`/`STATUS` are point-to-point.
- **Status exchange (one-directional).** The connector sends `GET_STATUS` after
  `connect_peer()`; the responder replies `STATUS`. This needs no change to
  `kwartel.net` and is sufficient: a shorter connector learns the responder's
  taller tip and requests it, then orphan rescue fetches ancestors. Documented
  as a deliberate simplification.
- **Hostile input.** `_dispatch` catches `struct.error`/`IndexError`/`ValueError`
  (malformed deserialize) and disconnects only that peer; the node never crashes.
- **Transport shutdown hardening.** `kwartel/net` was hardened so shutdown cannot
  hang: `Peer.close()`/`Server._close_writer` bound `wait_closed()` to 2s,
  `Server.stop()` tracks and cancels inbound handler tasks (and bounds its own
  `wait_closed()`), and `Peer.send` bounds each write to 5s. `NetNode`'s reader
  loop blocks on `server.receive()` (no busy polling) and is cancelled on stop.

## Test results

`pytest tests/ -q` passes all 174 tests (167 existing + 7 new). Phase 1
node/bus tests are untouched and still green after the `gossip.py` extraction.

## Files created

- `kwartel/node/gossip.py`
- `kwartel/node/netnode.py`
- `kwartel/node/cluster.py`
- `tests/node/test_gossip.py`
- `tests/node/test_partition_tcp.py`

## Files modified

- `kwartel/net/framing.py` (extended `TOPICS`: BLOCK=6, TX=7, INV_BLOCK=8, GET_BLOCK=9, GET_STATUS=10, STATUS=11)
- `kwartel/net/server.py` (shutdown hardening: bounded `wait_closed`, inbound-task tracking)
- `kwartel/net/peer.py` (bounded close/write waits)
- `kwartel/node/node.py` (`_handle` now delegates to `gossip.handle_message`)
- `kwartel/node/miner.py` (extracted `build_and_add_block`)
- `kwartel/node/__main__.py` (rewritten for the TCP five-act demo)
- `kwartel/node/README.md` (extended)

## Deviations / interpretations

- **Test 2 funding.** The spec's "premine from genesis dev key" cannot be used:
  the genesis dev *secret* is discarded (`genesis.py`). I fund by generating a
  fresh miner key and mining a funding block, identical to the Phase 1 pattern.
- **Ticker.** The demo prints `SHAP` (the locked coin ticker); the codebase's
  smallest-unit constant is still named `KWARTS_PER_KWT`, a naming migration
  left for a later task.
- **`data_dir`** in `NetNode.__init__` is treated as the node's SQLite DB file
  path (consistent with `FullNode.db_path`).

---

# Phase 2 Task 03 — Peer Discovery & Initial Chain Sync Findings

## Standing rule applied

No secret keys are printed in the demo or this section. Only node heights,
block-hash prefixes, and balances are shown.

## Demo output (`python -m kwartel.node`, Act 6 tail)

```
... (Acts 1–5 unchanged from Task 02, network at height 7)

Act 6: cold join (fresh node3 knows only node1's address)
  node node0: height=7 tip=00f405058a1d9fb7...
  node node1: height=7 tip=00f405058a1d9fb7...
  node node2: height=7 tip=00f405058a1d9fb7...
  node node3: height=7 tip=00f405058a1d9fb7...
  node3 synced to tip: True
  node3 Bob balance: 30 SHAP

PHASE 2 TASK 03 COMPLETE: fresh node cold-joined and synced to tip.
[node3] IBD complete at height 7
```

(Tip hashes vary per run because each boot generates fresh keys.)

## Design notes

- **Peer exchange.** `GET_PEERS`/`PEERS` (topics 12/13) carry a
  `u16 count` then `u8 host_len + host + u16 port` per entry, capped at 64.
  Every completed handshake triggers `GET_PEERS` on both sides (via a new
  `Server.on_peer_connected` hook); `PEERS` is validated strictly and merged
  into the `AddressBook`. A periodic tick re-asks a random peer.
- **Address book** (`discovery.py`). `AddressBook` dedups on `(host, port)`,
  caps at 1000 (evict oldest `"peer"`, then `"observed"`; `"configured"` never),
  tracks failures (drop non-configured at 5), and persists to `peers.json`
  (corrupt file → empty book, no crash). `serialize_peers`/`deserialize_peers`
  are pure and unit-tested.
- **SyncPlanner** (`sync.py`). A pure, socket-free state machine: `plan()`
  requests the tallest peer tier's tip (up to `MAX_IN_FLIGHT=8`), `expire()`
  drops timed-out requests, `is_done()` is true when we match the tallest
  peer's height and tip. No validation logic — blocks still flow through
  `chain.add_block`.
- **IBD = automated GET_BLOCK + orphan rescue (no `GET_BLOCKS`).** The spec
  asked me to decide whether one-block-at-a-time ancestor fetching is fast
  enough. For this task's scale (10 blocks in the gate test, 7 in the demo) it
  is: `SyncPlanner` requests the tip, the existing orphan buffer walks
  ancestors. No new `GET_BLOCKS` topic was needed; documented here.
- **Status exchange is one-directional** (connector learns the responder's
  status), which needs no change to `kwartel.net` and suffices for sync and the
  taller-peer request.
- **Shutdown hardening.** An intermittent Windows Proactor hang was found and
  fixed: the reader loop could block on an outbound `open_connection` during
  teardown and never respond to cancellation. Fixes: (1) outbound connects are
  spawned as tracked background tasks, never awaited inline in the reader loop;
  (2) `Peer.close`/`_close_writer` are fire-and-forget (no `wait_closed`);
  (3) `stop()` uses bounded `asyncio.wait(..., timeout=2.0)` instead of
  unbounded `await task`/`gather`; (4) `NetNode.stop()` closes the SQLite
  `BlockStore` so the DB file is released before cleanup.

## Test results

`pytest tests/ -q` passes all 202 tests (174 existing + 28 new: 18 discovery,
10 sync). Nothing broken.

## Files created

- `kwartel/node/discovery.py`
- `kwartel/node/sync.py`
- `tests/node/test_discovery.py`
- `tests/node/test_sync.py`

## Files modified

- `kwartel/net/framing.py` (extended `TOPICS`: GET_PEERS=12, PEERS=13)
- `kwartel/net/peer.py` (`listen_port`/`host`; fire-and-forget close)
- `kwartel/net/server.py` (`on_peer_connected` hook; bounded shutdown)
- `kwartel/node/netnode.py` (discovery + IBD wiring)
- `kwartel/node/cluster.py` (`add_node` passthrough for configured peers/config)
- `kwartel/node/__main__.py` (Act 6 cold join)
- `kwartel/node/README.md` (extended)

## Deviations / interpretations

- **No `GET_BLOCKS`** (one-at-a-time ancestor fetch is sufficient at this scale).
- **`peers.json` path** derived from the DB file path (`node0.db` →
  `node0.peers.json`).
- **`test_sync_timeout_retry`** uses a "mute" raw asyncio server (handshakes and
  answers `STATUS`/`PEERS` but never `GET_BLOCK`) so the retry-via-another-peer
  path is exercised deterministically.
- **Shutdown race** (Windows Proactor `open_connection` cancellation) was
  discovered during this task and fixed as described above; the fix also
  benefits Task 02's shutdown.





