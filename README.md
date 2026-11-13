# Kwartel

A UTXO blockchain built from scratch in Python — Ed25519 signatures, SHA-256, Merkle trees, CPU proof-of-work, and a peer-to-peer TCP gossip network.

**202 tests passing** (`pytest tests/ -v`).

> **Status:** Phase 1 (chain) and Phase 2 (networking) are complete.
> Phase 3 is a Rust port for performance and it **has not been started** — this repository contains Python only.

This is an educational systems project, not a launched currency. There is no token sale, no network to join, and no financial claim attached to it. The point is the protocol.

---

## Why build a blockchain by hand

The project exists to understand consensus from the wire protocol up rather than hide behind a framework. Four rules drove every decision:

1. **Known cryptography, novel architecture.** SHA-256 and Ed25519 from audited libraries (`PyNaCl`). Primitives are never invented.
2. **Tests before code.** No module ships without a failing test first. That is where the 202 tests come from.
3. **Prove the boring version works before innovating.** v0.1 is deliberately a small, clean, readable chain.
4. **Treat hostile input as the normal case.** Consensus code parses untrusted data from the network, so validation *returns violations* instead of raising — a malformed signature should never be able to crash a node.

---

## Architecture

| Package | Responsibility |
|---|---|
| `kwartel/crypto` | Ed25519 keypairs, detached signatures, SHA-256 helpers, Base58Check addresses |
| `kwartel/transaction` | UTXO transaction model, validation rules, UTXO set, mempool |
| `kwartel/blockchain` | Blocks, headers, Merkle trees, proof-of-work, coinbase, chain persistence |
| `kwartel/net` | TCP transport — length-prefixed binary framing, magic/genesis handshake, peer lifecycle |
| `kwartel/node` | Node behaviour — gossip, peer discovery, chain sync, miner, partition simulation |

Each package carries its own README explaining **why** it is built the way it is, not just what it does. Those are the substantive docs; this file is the front door.

---

## Quickstart

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # pynacl + pytest

# run the full suite — 202 tests
.venv/Scripts/python.exe -m pytest tests/ -v
```

Each package has a runnable demo that exercises it end to end:

```bash
python -m kwartel.crypto        # keypair, sign, verify, Base58Check address
python -m kwartel.transaction   # build a transaction, validate, apply to the UTXO set
python -m kwartel.blockchain    # mine a block, check difficulty, verify the Merkle root
python -m kwartel.net           # two TCP nodes handshake and exchange a ping/pong
python -m kwartel.node          # multi-node scenario over real TCP: gossip, partition, heal
```

---

## Design notes

A few decisions worth calling out, each covered in depth in the relevant package README:

- **UTXO, not accounts.** Balances are not stored by the protocol; a wallet's balance is the sum of unspent outputs it can unlock. This makes double-spends explicit — an output can be spent once, ever.
- **The txid excludes signatures.** If signatures were hashed into the txid, each signer would need every other signature before signing their own input. Excluding them lets every input sign the same txid independently.
- **Conservation is the rule that prevents minting.** Total outputs may never exceed total inputs, and the difference (the fee) must be ≥ 0.
- **Length-prefixed framing, not a delimiter.** Payloads are arbitrary binary, so a delimiter would need escaping — and escaping bugs are a classic source of framing attacks. Every message is `[u32 LE payload_len][u16 LE topic_id][payload]`, capped before allocation.
- **Odd-node duplication follows CVE-2012-2459.** The Merkle implementation handles the odd-node case the way Bitcoin had to learn to.
- **Interoperability with the existing implementation matters.** A `verify()` that returns `False` rather than raising keeps verification a pure boolean decision for callers.

---

## Test coverage

The 202 tests are organised by package and include adversarial cases rather than only happy paths:

- crypto — key derivation, sign/verify round-trips, signature rejection, address checksums
- transaction — validation failures, conservation, double-spend prevention at both the mempool and UTXO set
- blockchain — difficulty, Merkle roots, genesis, persistence, coinbase rules
- net — framing, truncated payloads, handshake rejection
- node — gossip propagation, discovery, sync, partition and heal, TCP partitions

---

## Roadmap

- **Phase 3 — Rust port** (not started; the Python implementation is the deliverable today)
- RPC/API layer for a wallet and a block explorer
- An attack lab: an adversarial suite aimed specifically at the consensus rules

---

## Licence

MIT — see `LICENSE`.
