# Project Kwartel (KWT) — Phase 1, Task 03: Blocks & Merkle Trees

> **Model tier:** DeepSeek V4 Pro (consensus-critical). Block hashing and Merkle
> roots are consensus data — a single nondeterministic byte breaks the chain.
>
> **Cline instructions:** Read this file fully before coding. TDD strictly:
> test → fail → implement → pass, per task. Append to `FINDINGS.md`, never
> overwrite. Do NOT git commit. Never log secret keys.

## Context

Tasks 01–02 are accepted: crypto module + UTXO transactions/mempool. Now we
build the block: a header that commits to everything (previous block, Merkle
root of transactions, timestamp, difficulty, nonce) plus the transaction list.
This is the structure that makes tampering cascade: change anything in an old
block and every later header hash becomes invalid.

## Deliverables

### Files
- `kwartel/blockchain/__init__.py`
- `kwartel/blockchain/merkle.py` — Merkle tree
- `kwartel/blockchain/block.py` — Block/Header model + serialization
- `kwartel/blockchain/genesis.py` — genesis block construction
- `kwartel/blockchain/__main__.py` — demo
- `kwartel/blockchain/README.md` — design note
- `tests/blockchain/test_merkle.py`, `test_block.py`, `test_genesis.py`

### Part A: Merkle tree (merkle.py)

- `merkle_root(txids_hex: list[str]) -> str` — hex root of the txid list.
- Pairwise: `parent = sha256(left_bytes + right_bytes)` where txids/hashes are raw 32-byte digests internally (decode hex, hash, re-encode).
- **Odd node duplication:** if a level has an odd count, duplicate the LAST node (Bitcoin-style). This is a known weakness in Bitcoin (CVE-2012-2459 — duplicate-leaves forgery); we duplicate it anyway for simplicity BUT write a test documenting the behavior, and the README must explain the CVE and why block-level validation (validating txs in the block, not trusting the root alone) neutralizes it for us.
- Single tx → root = its own hash... define precisely: for one element, root is `sha256(leaf + leaf)` after duplication rule OR the leaf itself — **choose: apply the duplicate rule uniformly (levels of 1 duplicate themselves, so a single tx yields sha256(leaf||leaf))**. Document the choice and test it. Consistency matters more than which choice.
- Empty list → root of all-zero bytes: `sha256(b"")` — define and test.
- Tests: known 4-leaf vector (compute by hand in the test), odd counts at multiple levels, order sensitivity (swapping two txids changes root), determinism.

### Part B: Block model (block.py)

```python
@dataclass(frozen=True)
class BlockHeader:
    prev_block_hash: str   # hex of previous header hash; all-zero-hash for genesis handled by genesis module
    merkle_root: str       # hex
    timestamp: int         # unix seconds, int only
    difficulty: int        # leading zero BITS required on header hash (see Part C)
    nonce: int             # u64

@dataclass(frozen=True)
class Block:
    header: BlockHeader
    transactions: tuple[Transaction, ...]

def serialize_header(h: BlockHeader) -> bytes:
    # canonical, length-prefixed like serialize_tx:
    # prev(32 raw via len-prefix) , merkle(32 raw), timestamp(u64 LE), difficulty(u32 LE), nonce(u64 LE)

def block_hash(header: BlockHeader) -> str:  # sha256(serialize_header), hex
```

- `Outpoint.index` lesson applied: validate ranges explicitly. Add `validate_block_structure(block) -> list[str]` (never raises) checking: timestamp is int ≥ 0, difficulty ≥ 1, nonce in [0, 2^64), transactions non-empty OR is coinbase-only block (define `is_coinbase_only`), every tx's structure sanity (outputs exist, values ≥ 1... reuse light checks; full tx validation against UTXO set comes in Task 04).
- No floats anywhere. Timestamps int only.

### Part C: Proof-of-Work + difficulty (block.py)

- `meets_difficulty(header) -> bool`: `block_hash` hex must have at least `difficulty` **leading zero bits**. Implement bit-accurate (convert hash int, or check per-character on bits — write a helper `leading_zero_bits(hex_hash) -> int` and unit-test it thoroughly, including exactly-at-threshold cases).
- `mine_block(header_template, max_nonce=2**64) -> BlockHeader`: loop nonce 0.. until `meets_difficulty`. Deterministic: same inputs → same result.
- Difficulty is expressed in BITS (e.g. difficulty=8 → 1/256 chance per nonce). Start low (8–12 bits) so demos mine in seconds.
- Tests: meets_difficulty boundary vectors, mine_block actually produces a valid header (with difficulty 8), determinism.

### Part D: Genesis (genesis.py)

- `create_genesis_block(payout: TxOutput) -> Block`: the chain's first block.
  - prev_block_hash = `"00" * 32`
  - Contains exactly ONE coinbase-shaped transaction (no inputs, one output = the initial premine payout to a fixed well-known dev pubkey passed by caller). `is_coinbase(tx)` from Task 02 must return True for it.
  - Fixed timestamp constant (e.g. `1757200000`) — genesis must be identical on every node forever. Difficulty: 8. Nonce: mine it once and **hardcode the result as a test vector** (test asserts the canonical genesis hash matches the hardcoded value — this pins consensus).
- Tests: genesis is deterministic (same input → same hash), passes `validate_block_structure`, coinbase shape recognized, hardcoded-hash pin test.

### Part E: Demo (`__main__.py`)

Build genesis → construct a second block containing 2–3 real signed transactions spending the premine (reuse `Transaction.create` + `UTXOSet` from Task 02) → mine it at difficulty 8 → print block hash, merkle root, nonce, mining time, and `leading_zero_bits` of the hash. Then tamper with one transaction and show that (a) the merkle root changes and (b) the block hash no longer meets difficulty. Paste output into FINDINGS.md.

## Acceptance criteria

1. `pytest tests/ -v` all green (63 existing + new)
2. All hashing/serialization deterministic; no floats; no dict-ordering dependence
3. `validate_block_structure` never raises
4. README: explain Merkle trees (why they let light clients verify inclusion with log(n) hashes), the odd-duplication CVE tradeoff, why the header commits to prev hash (tamper cascade), what difficulty bits mean, why genesis must be pinned
