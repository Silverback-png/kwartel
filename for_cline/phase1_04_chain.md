# Project Kwartel (KWT) — Phase 1, Task 04: Blockchain, Validation & Persistence

> **Model tier:** DeepSeek V4 Pro preferred (consensus-critical). This module
> decides what "the truth" is: which chain wins, what makes a block valid, and
> whether state survives a restart. Bugs here are the most expensive kind.
>
> **Cline instructions:** Read fully before coding. TDD strictly per task.
> Append to `FINDINGS.md`. No git commits. Never log secret keys.
> int only, no floats. Validation never raises on bad input — returns violations.

## Context

Tasks 01–03 accepted: crypto, UTXO transactions/mempool, blocks/Merkle/PoW with
pinned genesis. Now we connect blocks into THE blockchain: append-only storage,
full block validation (transactions checked against the UTXO set that the chain
itself produces), coinbase economics, retargeting-free fixed difficulty (Phase 1
only), and longest-chain fork choice with explicit reorg handling.

Key mental model: **the chain state is derived, not stored.** The UTXO set at
block N is computed by replaying blocks 1..N from genesis. Persistence stores
blocks; the UTXO set is rebuilt or updated by applying blocks in order.

## Deliverables

### Files
- `kwartel/blockchain/chain.py` — Chain class: storage + validation + fork choice
- `kwartel/blockchain/persistence.py` — SQLite block store
- `kwartel/blockchain/coinbase.py` — coinbase construction + coinbase validation rules
- `kwartel/blockchain/__main__.py` — extend the existing demo (keep the old demo working)
- `kwartel/blockchain/README.md` — extend design note
- `tests/blockchain/test_chain.py`, `test_persistence.py`, `test_coinbase.py`

### Part A: Coinbase economics (coinbase.py)

- `COINBASE_MATURITY = 1` (coinbase output may not be spent until 1 block deep — i.e., not in the very block... for Phase 1, enforce: a coinbase output can be spent only if the coinbase tx is at least `COINBASE_MATURITY` blocks deep; implement the check, test it).
- `create_coinbase(block_height: int, payout_pubkey: bytes, fee_total: int) -> Transaction`:
  no inputs, exactly one output: value = `BLOCK_REWARD + fee_total`.
  - `BLOCK_REWARD = 50 * KWARTS_PER_KWT`. Include the block height inside the coinbase serialization — simplest: encode height in a dedicated lock-prefix? NO — cleanest for our model: coinbase txids would collide across blocks if identical, so add height to the txid preimage. Implement by adding an OPTIONAL `coinbase_height: int | None = None` field to `Transaction`? — NO, do not modify Task 02 dataclasses. Instead: put the height in the coinbase's single output `lock`? NO.
  - **Solution:** the coinbase tx carries a zero-value-free trick: make the output `value=BLOCK_REWARD+fee_total` and rely on the block's height + prev hash making the block unique; duplicate coinbase txids across blocks are acceptable in Phase 1 ONLY IF we detect double-claim: `validate` rejects a second coinbase spending the same... — simplest correct approach for Phase 1: **allow duplicate coinbase txids but track coinbase outpoints by (block_hash, txid, index)** in the UTXO set — they never collide because block hash is unique. Document this decision.
- `validate_coinbase(tx, block, expected_reward_context) -> list[str]`: exactly one output, no inputs, value == BLOCK_REWARD + declared fees, no other coinbase in the block.
- Tests: reward math, maturity enforcement, coinbase in block position 0 (first tx must be the coinbase — enforce in chain validation).

### Part B: Persistence (persistence.py)

SQLite via stdlib `sqlite3`, file `kwartel_chain.db` (in a `data/` dir, gitignored):

- `BlockStore` class: `save_block(block)`, `get_block(hash) -> Block | None`, `get_block_by_height(height)`, `height() -> int`, `has_block(hash) -> bool`, `iter_blocks_from_height(h)`.
- Serialize blocks as: header fields + tx count + each tx's canonical serialization (reuse `serialize_tx` with signatures). Store `txids` too for reconstruction. Roundtrip test: save → load → identical block (assert header hash + all txids + serialization equality).
- Store metadata table: `tips` (see Part C), `height`.
- **Index on hash and height.** Test with ≥ 10 blocks.

### Part C: Chain (chain.py) — the core

```python
class Chain:
    def __init__(self, store: BlockStore): ...
    def add_block(self, block: Block) -> list[str]   # [] = accepted; violations otherwise
    def tip(self) -> Block                            # best (heaviest/longest) block
    def height(self) -> int
    def balance(self, pubkey: bytes) -> int           # via UTXO set at tip
    def utxo_set(self) -> UTXOSet                     # rebuilt lazily/cached at tip
```

- Initialize from genesis: on first run, create + store pinned genesis (from `genesis.py`, with `GENESIS_PAYOUT`). On subsequent runs, load from store and rebuild UTXO state by replay (cache the tip UTXO set in memory, invalidate on reorg).
- `add_block` full validation (each rule = a test):
  1. `validate_block_structure` passes (reuse Task 03)
  2. `prev_block_hash` equals an existing block's hash (parent known)
  3. Header hash meets `difficulty`
  4. Block's merkle root matches recomputed root of its txids
  5. First tx is coinbase; exactly one coinbase; `validate_coinbase` passes
  6. Every non-coinbase tx passes `validate_tx` **against the UTXO set as of the parent block** (i.e., parent state + earlier txs in this block)
  7. No tx in the block spends an output created in the same block's coinbase (maturity = 1 handles this)
  8. Timestamp: `block.timestamp > parent.timestamp` (monotonic, Phase 1 simple rule)
- **Fork choice: longest chain.** `self.tips` tracked in the store; on add_block, if the new block's chain is longer than the current tip's → **reorg**: rebuild UTXO set from genesis replaying the new chain. Implement `_replay_to_height(h) -> UTXOSet` and use it for reorgs. Return violations on reject.
- Reorg tests (critical): build chain A (2 blocks) and competing chain B (3 blocks on the same parent). After adding B's blocks, tip must be B's head, UTXO set must reflect B, and a tx spend that was valid in A but not B must be gone. Also test that a shorter fork is NOT adopted.
- `balance()` and `utxo_set()` always reflect the tip.

### Part D: Demo extension (`__main__.py`)

Extend: mine a small chain (genesis + 4 blocks, each collecting the mempool's txs + coinbase), print height/tip hash/balances per block. Then demonstrate a reorg: build a 5-block fork that overtakes, show tip switch + balances change. Persist, close, **reopen in a fresh Chain object and show state restored** (height + balances identical). Output to FINDINGS.md.

## Acceptance criteria

1. `pytest tests/ -v` all green — previous 98 + new suite, nothing broken
2. Restart survives: fresh `Chain` from the same db file reproduces height + tip hash + balances exactly
3. Reorg test proves tip/UTXO switching
4. No floats, no wall-clock `time.time()` in validation logic (mining demo may use time for measuring, never inside block data)
5. README additions: why state is derived not stored, what a reorg is, why coinbase maturity exists, why first-tx-must-be-coinbase
