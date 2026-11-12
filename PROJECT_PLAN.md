# KWARTEL CHAIN / SHAP COIN — Master Project Plan

> Status: v2 — CHAIN = Kwartel (the quail), COIN = SHAP ("shap" — provision/OK). Stack locked: Python 3.11 → Rust, Ed25519, SHA-256, UTXO, CPU PoW baseline
> Workspace: C:\Users\TTEMPESTT\kwartel\

## Philosophy (non-negotiable)

1. **Known crypto, novel architecture.** SHA-3/BLAKE3 for hashing, Ed25519 or secp256k1 for signatures. Never invent primitives.
2. **Module by module, tests before code.** No component ships without failing-test-first and passing.
3. **Prove the boring version works before innovating.** v0.1 is deliberately a clean, small, educational chain.
4. **The attack lab is a first-class deliverable**, not an afterthought. Consensus isn't "done" until we've tried to break it.

## Tech Stack (proposed)

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11 (Phase 1) → Rust port (Phase 3+) | Fast iteration while learning; Rust for real performance/typo-safety later |
| Crypto | `pynacl` (Ed25519), `hashlib`/BLAKE3 | Audited libs only |
| Storage | SQLite → LMDB later | Simple, persistent, easy to inspect |
| P2P | `asyncio` + raw TCP, custom wire protocol (Phase 1); libp2p-style later | Learn the protocol rather than hiding behind a framework |
| Tests | pytest | Already our toolchain |
| RPC/API | JSON-RPC over HTTP (FastAPI) | Explorer + wallet talk to this |

## Repository Layout (target)

```
kwartel/
├── kwartel/
│   ├── crypto/        # keys, signatures, hashing
│   ├── transaction/   # tx model, validation, mempool
│   ├── blockchain/    # blocks, headers, merkle, chain, validation
│   ├── consensus/     # PoW engine, difficulty, (later: Kwartel consensus)
│   ├── network/       # node, peer discovery, wire protocol, sync
│   ├── storage/       # persistent chain state
│   ├── rpc/           # JSON-RPC server
│   └── wallet/        # CLI wallet
├── tests/             # mirrors package layout
├── attacklab/         # simulations: adversaries, partitions, reorgs
├── docs/              # design docs — every major decision gets one
└── explorer/          # web explorer (Phase 6)
```

## Phases

### Phase 1 — Educational chain (local, single machine, 3 simulated nodes)
- [ ] Crypto: Ed25519 keypairs, sign/verify
- [ ] Transaction model (UTXO first — simpler to reason about than accounts)
- [ ] Mempool + validation rules
- [ ] Block + header + Merkle tree
- [ ] Chain + full validation + persistence (SQLite)
- [ ] CPU PoW (SHA-256), retargeting difficulty
- [ ] Fork-choice: heaviest/longest chain
- [ ] CLI: `kwarteld`, `kwartel-wallet`
- [ ] 3-node simulated network demo end-to-end

### Phase 2 — Real P2P
- [ ] TCP wire protocol, peer discovery, handshake
- [ ] Block/tx propagation, chain sync (headers-first)
- [ ] Partition + reorg handling
- [ ] Test on 2 real machines

### Phase 3 — Attack Lab v1
- [ ] Simulated adversary framework (hash power %, Sybil, latency, packet loss)
- [ ] 51% simulation, selfish mining, double-spend attempts
- [ ] Fix what breaks; document everything

### Phase 4 — Testnet + economics design
- [ ] Public testnet, anyone runs a node
- [ ] Coin economics: supply, issuance schedule, fees — designed deliberately, documented

### Phase 5 — Wallet (GUI) + Explorer

### Phase 6 — The novel part
- [ ] Research: PoR (Proof-of-Resource), heterogeneous CPU/GPU/RAM/storage proofs, DAG structures
- [ ] Formal security properties per design; simulation before implementation

## Open Decisions (owner: Drikus)
1. **Language:** Python-first-then-Rust (recommended) vs straight Rust vs Go?
2. **Ledger model:** UTXO (recommended for v0.1) vs account-based?
3. **Consensus for v0.1:** plain SHA-256 CPU PoW (recommended baseline)?
4. **Coin parameters:** chain=Kwartel, ticker=SHAP (no existing crypto collision; 1 SHAP = 10^8 kwarts smallest unit). Supply/decimals — defer to Phase 4.

## Rules of engagement for Hermes
- Every module: design doc → failing tests → implementation → pass → security review pass.
- No fabricated results: all demos must be real program output.
- All git work stays local until explicitly told otherwise.
