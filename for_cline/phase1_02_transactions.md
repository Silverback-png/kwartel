# Project Kwartel (KWT) — Phase 1, Task 02: UTXO Transaction Model

> **Model tier:** DeepSeek V4 Pro (consensus-critical). This module IS the money.
> A bug here means theft or minting coins from nothing. Take the extra care.
>
> **Cline instructions:** Read this file completely before writing any code.
> TDD strictly: each test written first, run to fail, then implement, then pass.
> Append progress + deviations to `FINDINGS.md` (never overwrite).
> Do NOT git commit.
>
> **NEW STANDING RULE:** Never log, print, or write secret keys anywhere —
> including demos and FINDINGS.md. Public keys and addresses are fine.

## Context

Task 01 (crypto module) is complete and accepted. Now we build the transaction
model: **UTXO (Unspent Transaction Output)**, Bitcoin-style.

Mental model: there are no "accounts" or "balances" stored anywhere. A wallet's
balance is computed by scanning all unspent outputs it can unlock. Spending
means consuming whole outputs and creating new ones. Change must be sent back
to yourself explicitly.

```
Transaction
├── inputs:   [ (prev_txid, output_index, unlock: signature+pubkey) ]   # what you consume
├── outputs:  [ (value, lock: address/pubkey) ]                          # what you create
└── fee = sum(inputs.value) - sum(outputs.value)   # >= 0, goes to miner
```

Two invariants the whole security of the chain rests on:
1. **Conservation:** total value out ≤ total value in (fee is the difference). No minting.
2. **No double-spend:** each output can be consumed exactly once, ever.

## Setup

Work in `C:\Users\TTEMPESTT\kwartel` with the existing `.venv`.

## Deliverables

### Files
- `kwartel/transaction/__init__.py`
- `kwartel/transaction/model.py` — dataclasses + canonical serialization
- `kwartel/transaction/validation.py` — the rules (security-critical)
- `kwartel/transaction/utxo_set.py` — the UTXO set (in-memory for now; persistence comes later)
- `kwartel/transaction/mempool.py` — pending transactions
- `kwartel/transaction/__main__.py` — demo
- `kwartel/transaction/README.md` — design note (see end)
- `tests/transaction/test_model.py`, `test_validation.py`, `test_utxo_set.py`, `test_mempool.py`

### Part A: Model (model.py)

```python
@dataclass(frozen=True)
class Outpoint:      # reference to one output
    txid: str        # hex, 64 chars
    index: int       # output index within that tx

@dataclass(frozen=True)
class TxOutput:
    value: int       # in "kwarts" (smallest unit; 1 KWT = 10^8 kwarts). int only — NEVER float
    lock: bytes      # locking script/pubkey — keep simple: the recipient's 32-byte public key

@dataclass(frozen=True)
class TxInput:
    outpoint: Outpoint
    unlock_pubkey: bytes   # 32-byte pubkey proving ownership
    signature: bytes       # 64-byte Ed25519 signature

@dataclass(frozen=True)
class Transaction:
    inputs: tuple[TxInput, ...]    # tuple, not list — immutability matters for hashing
    outputs: tuple[TxOutput, ...]
```

- `txid(tx: Transaction) -> str`: SHA-256 of the canonical serialization of the tx **with all signatures set to empty bytes**, hex-encoded. (Signing input must exclude signatures — otherwise circular hash. This is standard.)
- Canonical serialization: implement `serialize_tx(tx, include_signatures: bool) -> bytes` with a **length-prefixed encoding** — every field: `len(u32 LE) + bytes`. Deterministic order: inputs in listed order, then outputs. No JSON. Test that serialization is stable and signature-independent when `include_signatures=False`.
- Use `int.to_bytes`/`from_bytes` with fixed 8-byte LE for values. Reject negative values at construction time (see validation).
- Provide `Transaction.create(...)` helper that assembles + signs inputs given a dict of available outputs and the signer's key, returning a fully signed tx (this is a convenience for tests/wallet, not validation logic).

### Part B: Validation rules (validation.py)

`validate_tx(tx, utxo_set, *, allow_coinbase=False) -> list[str]` — returns a list of **all** violations (empty list = valid). Never raises. Rules, each with a dedicated test:

1. Non-empty inputs and non-empty outputs (a tx with neither is meaningless)
2. Every input's outpoint must exist in the UTXO set
3. No duplicate outpoints within the tx (self-double-spend)
4. Unlock pubkey must derive to the address that the referenced output's lock contains — for Task 2, `TxOutput.lock` stores the owner's 32-byte public key; input's `unlock_pubkey` must equal it exactly
5. Signature must verify: `verify(unlock_pubkey, txid_bytes, signature)` where txid_bytes is the raw 32-byte digest (not hex)
6. Sum(outputs.value) ≤ sum(inputs.value) — conservation. Fee = difference, must be ≥ 0
7. Every value ≥ 0 (a negative output is an inflation bug)
8. Output value > 0 (dust = 0-value outputs rejected for now)
9. If `allow_coinbase` is False and the tx is a coinbase shape (empty inputs), reject. Coinbase validation itself comes with blocks (Task 03) — but define `is_coinbase(tx) -> bool` now: no inputs.

### Part C: UTXO set (utxo_set.py)

In-memory class `UTXOSet` backed by `dict[Outpoint, TxOutput]`:

- `add_output(outpoint, output)`
- `spend(outpoint) -> TxOutput` (raises KeyError if missing — callers must check first)
- `apply_transaction(tx) -> None` — validate first (raises ValueError listing violations if invalid), remove spent outpoints, add outputs keyed `(txid(tx), i)`
- `balance(pubkey: bytes) -> int` — total value of outputs locked to this pubkey
- `__len__`, `contains(outpoint)`
- Tests: spend consumed output disappears; balance computes correctly across multiple txs; double-spend attempt within one tx rejected; double-spend across two txs rejected by the second `apply_transaction`.

### Part D: Mempool (mempool.py)

`Mempool` class: `dict[txid, Transaction]` of valid-but-unmined txs.

- `accept(tx, utxo_set) -> bool` — validate against utxo_set; also reject if **any input is already consumed by a tx in the mempool** (the classic double-spend race — test it explicitly: same outpoint in two different txs, second must be rejected)
- `remove(txid)`, `get(txid)`, `all_transactions()`, `__len__`
- Simple for now; fee-priority sorting comes with the block builder.

### Part E: Demo (`__main__.py`)

Script: create two keypairs (Alice, Bob), fund Alice via a "genesis-style" manually-added UTXO, Alice sends 50 KWT to Bob with change back to herself, print the tx (txid, fee, addresses NOT raw pubkeys), show UTXO set before/after, show Bob's balance. Try a double-spend and print that it was rejected. Paste output in FINDINGS.md.

## Acceptance criteria

1. `pytest tests/ -v` — all pass (22 old + new suite, nothing broken)
2. Zero floats anywhere near money; int only
3. Validation returns violation lists, never raises on bad input
4. No secret material ever printed
5. README design note: explain UTXO vs account model, why txid excludes signatures, why conservation matters, what a double-spend is and the two places we stop it (mempool + UTXO set), and why fees must be ≥ 0.
