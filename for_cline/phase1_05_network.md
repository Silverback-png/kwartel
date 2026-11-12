# Project Kwartel (KWT) — Phase 1, Task 05: Three-Node Network Demo

> **Model tier:** Kimi K2.7 Code is fine — this is integration/plumbing, not new
> consensus code. All validation logic already exists and must be REUSED, not
> reimplemented. If you find yourself copying validation code, STOP — import it.
>
> **Cline instructions:** Read fully before coding. TDD where behavior is
> testable. Append to `FINDINGS.md`. No git commits. Never log secret keys.

## Context

Phase 1 finale. We have: crypto, UTXO txs, blocks, PoW, chain with fork choice
and persistence. Now we prove the full node story: **three independent nodes,
each with its own chain + mempool + keys, exchanging blocks and transactions
over a simulated network, converging on one chain, surviving a partition and a
reorg.** Everything runs in one process (real TCP is Phase 2).

Architecture:

```
NetworkBus (in-memory message bus)
   ├── Node A (own BlockStore in tmp dir, own Chain, own Mempool, own wallet keys)
   ├── Node B (...)
   └── Node C (...)
```

## Deliverables

### Files
- `kwartel/node/__init__.py`
- `kwartel/node/network.py` — NetworkBus (message passing)
- `kwartel/node/node.py` — FullNode class
- `kwartel/node/miner.py` — mining loop
- `kwartel/node/wallet.py` — thin wallet wrapper over existing crypto
- `kwartel/node/__main__.py` — the 3-node demo
- `kwartel/node/README.md` — design note
- `tests/node/test_bus.py`, `test_node.py`, `test_mining_sync.py`, `test_partition.py`

### Part A: NetworkBus (network.py)

Synchronous in-memory pub/sub. No threads required (deterministic is better for
Phase 1) — but structure it async-ready:

- `NetworkBus`: nodes register with `register(node_id) -> Mailbox`. A `Mailbox`
  has `send(topic, payload)` (to all others) and `drain() -> list[Message]`
  (own queue). Messages: `("BLOCK", serialized_block)`, `("TX", serialized_tx)`,
  `("INV_BLOCK", block_hash)`, `("GET_BLOCK", block_hash)` — define exactly
  these four; payload is canonical bytes (reuse serialize_block/serialize_tx).
- Delivery is manual: `bus.flush()` delivers all queued sends to recipient
  queues. Tests control ordering explicitly. No hidden concurrency.

### Part B: FullNode (node.py)

```python
class FullNode:
    def __init__(self, node_id: str, db_path: Path, bus: NetworkBus): ...
    def submit_tx(self, tx) -> bool            # to own mempool, then broadcast TX
    def handle_messages(self) -> int           # drain mailbox, process each, return count
    def height(self) -> int; def tip_hash(self) -> str; def balance(self, pubkey) -> int
```

- On `("TX", bytes)`: deserialize → mempool.accept(tx, chain.utxo_set()) → if
  accepted, nothing else (originator already broadcast).
- On `("BLOCK", bytes)`: deserialize → `chain.add_block(block)`; on success,
  remove included txs from mempool; on success ALSO broadcast INV_BLOCK.
- On `("INV_BLOCK", hash)`: if we don't have that block, send GET_BLOCK.
- On `("GET_BLOCK", hash)`: reply with BLOCK message if we have it.
- Duplicates must be idempotent (adding same block twice = no crash, no change).

### Part C: Miner (miner.py)

- `mine_once(node, coinbase_pubkey) -> Block | None`: take mempool txs (insertion
  order is fine), build block on node's tip with coinbase = REWARD + fees,
  mine at difficulty 8, `chain.add_block`, broadcast BLOCK. Return block.
- The miner must NOT include its own pending double-spends — mempool already
  guarantees non-conflicting inputs; rely on chain validation as the backstop.

### Part D: Wallet (wallet.py)

- `Wallet` class wrapping KeyPair: `new_address()`, `balance(node)`,
  `send_to(node, recipient_pubkey, amount_kwarts)` — builds tx via
  `Transaction.create` spending the wallet's UTXOs (fetch via
  `node.chain.utxo_set()` filtered by lock == pubkey; select until covered),
  submits to node. Raise on insufficient funds. No secret logging.

### Part E: Demo (`__main__.py`) — THE Phase 1 finale script

Script in numbered acts, output to FINDINGS.md:

1. **Boot:** 3 nodes, fresh dbs in `data/demo/`, one bus. Print each height/tip.
2. **Funding:** mine 1 block per node (each node's coinbase pays itself). Flush
   bus after each. All 3 nodes converge: same height, same tip hash.
3. **Payment:** Alice (keys on node A context) pays Bob 30 KWT via
   `wallet.send_to`; propagate tx (flush); each node mines one block; flush;
   show all nodes converged and Bob's balance consistent on all three.
4. **Partition:** bus.partition({A}, {B, C}) — A mines 2 blocks, B/C mine 3
   blocks. Flush within partitions only. Show the two competing tips.
5. **Heal:** bus.heal(); exchange missing blocks (the INV/GET handshake does
   this); flush until quiescent; show ALL nodes converged on B/C's longer chain
   (reorg happened on A) and balances match the B/C reality.
6. Print "PHASE 1 COMPLETE: 3 nodes converged after partition + reorg."

### Part F: README design note

Explain: why gossip/broadcast, what INV/GET solves, what a partition is, why
longest-chain heals it, and what a node stores locally.

## Acceptance criteria

1. `pytest tests/ -v` all green (128 + new)
2. Demo runs end-to-end and ends with the convergence line
3. No validation logic duplicated — imports from kwartel.blockchain/transaction only
4. Partition test asserts the reorg: node A's balances change to fork reality after heal
5. Deterministic: no sleeps, no threads; bus.flush() drives everything
