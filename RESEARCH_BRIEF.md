# KWARTEL CHAIN / SHAP COIN — Research Brief (2026-09-07)

> Researched by Hermes. Purpose: confirm scope, pick the right references,
> and lock the endgame before Phase 1 coding starts.

## 1. Reference codebases (study, don't copy)

| Project | Why it matters | Use for |
|---|---|---|
| **JoshOrndorff/blockchain-from-scratch** (Rust) | Cleanest from-scratch tutorial: hash → header/body split → consensus digest → PoW → signed txs | Structural blueprint for Phase 1 |
| **MiniChain** (StabilityNexus, Python) | Minimal educational Python chain, clean codebase | Python-first sanity reference |
| **Bitcoin Core** | The gold standard for validation rules, mempool policy, edge-case handling | Read when writing validation logic (Phase 2+) |
| **Chia** (chiapos / chia-blockchain) | Real-world proof-of-space-and-time — the most relevant *novel* consensus shipped this decade | Phase 6 design study |
| **Monero / RandomX** | Production memory-hard CPU PoW; hard-won ASIC-resistance lessons | Phase 6 + attack lab |

## 2. Key findings

### Consensus landscape
- **Memory-hard PoW is the mature "anti-GPU-farm" answer.** RandomX (CPU-first,
  needs ~2GB RAM + cache hierarchy) and Equihash (memory-bound) both work in
  production. Lesson from Zcash's Equihash tradeoff analysis: memory-hard
  functions only resist ASICs when (a) access patterns are genuinely
  pseudorandom, (b) required memory exceeds economical on-die SRAM, and
  (c) bandwidth approaches external memory interface limits. Design with all
  three, or an ASIC will exist within 18 months.
- **Proof-of-Useful-Work is hot but treacherous.** SoK 2025 (eprint 2025/1814)
  found most current PoUW mechanisms fall short on verifiability/security;
  promising directions: verifiable computation (ZK proofs as the work — see
  Nockchain, launched 2025) and utility-aware difficulty (arXiv 2504.09971:
  matrix-multiplication PoW — the exact op AI GPUs already burn energy on).
  This is the most credible lane for Kwartel's "novel" layer: **a GPU miner
  whose work doubles as verifiable AI-compute.**
- **Chia model** (proof of space + verifiable delay) is the other credible
  lane: storage instead of compute. Hardware: commodity HDDs. Verified by all
  nodes cheaply.

### Existing-name check (important)
- **"Aetheris (AETH)" already exists** — a scrypt PoW+PoS chain (aetherischain.com).
  Also Aethir (ATH, GPU DePIN), Aetherius (AETH). The AETH ticker is contested.
- **Resolved 2026-09-07:** chain named **Kwartel** (Afrikaans for quail — the bird
  God sent as provision alongside manna, Exodus 16). Coin ticker **SHAP** — SA slang
  for "sharp/sorted", and the provision itself. No crypto collision for either.

## 3. Endgame — the honest answer

Realistic ceiling, in order of certainty:
1. **Certain:** a working, tested, multi-node blockchain we fully understand.
   Educational + portfolio value. No caveats.
2. **Likely:** a private/testnet network with 5–20 nodes across your machines,
   with a wallet and explorer. Real product.
3. **Possible:** a genuinely novel consensus design (AI-useful-work GPU PoW or
   storage-hybrid), formally specified and validated in simulation. Publishable
   as research even if never a "real" coin.
4. **Unlikely (~coin-launch odds):** strangers running nodes and holding value.
   That requires years of security hardening, a community, and liquidity —
   and a chain is only as strong as its weakest week. We build AS IF possible
   (rigorous), but we don't promise it.

## 4. Locked technical choices (pending Drikus's confirm)

- **Language:** Python 3.11 for Phases 1–2 (velocity, learning), Rust port for
  Phase 3+ (performance, correctness — Rust is the industry standard for chains).
- **Crypto:** Ed25519 (pynacl) signatures, BLAKE3 or SHA-256 hashing. Nothing homemade.
- **Ledger:** UTXO (Bitcoin-style) — clearer double-spend semantics, testable.
- **v0.1 consensus:** SHA-256 CPU PoW, retargeting difficulty, heaviest-chain fork choice.
  Deliberately boring: it's the control group for the attack lab.
- **Novel layer (Phase 6 shortlist):** (a) AI-matmul useful-work PoW,
  (b) Chia-style space+time hybrid, (c) RandomX-style memory-hard CPU PoW.
  Chosen by simulation results in the attack lab, not by vibes.

## 5. Division of labor (locked)

- **Hermes:** research, design docs, architecture decisions, task specs, code review, attack-lab design and analysis.
- **Cline (VS Code):** all hard coding per task files in `<project>/for_cline/*.md`.
- **Cline writes FINDINGS.md; Hermes reviews.** Phased tasks APPEND to existing FINDINGS.md.
