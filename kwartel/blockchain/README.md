# kwartel.blockchain

Blocks, headers, Merkle trees, and proof-of-work for Kwartel.

## What is a block header?

A block header is a small, fixed-size structure that commits to everything
important in a block:

- `prev_block_hash`: the hash of the previous block's header
- `merkle_root`: a 32-byte digest summarising every transaction in the block
- `timestamp`: Unix seconds, integer only
- `difficulty`: how many leading zero bits the header hash must have
- `nonce`: a free u64 miners adjust to satisfy the difficulty

Because the header commits to the previous block hash, changing anything in an
old block changes that block's hash, which changes the next block's
`prev_block_hash`, which changes the next block's hash, and so on.  This is the
tamper cascade that makes blockchain history hard to rewrite.

## Why Merkle trees?

A Merkle tree lets the header commit to N transactions with a single 32-byte
root.  To prove that a transaction is in the block, a light client only needs
the transaction plus one sibling hash per tree level — O(log N) data instead of
the full block.  Internal nodes are hashed as `sha256(left || right)`.

## Odd-node duplication and CVE-2012-2459

When a level has an odd number of nodes, Kwartel duplicates the last node
(Bitcoin-style).  This is simple but has a known weakness: an attacker can
sometimes add duplicate leaves without changing the root.  We deliberately copy
Bitcoin's behaviour for compatibility, but we neutralise the attack by always
validating the actual transactions inside a block, not by trusting the Merkle
root alone.  A block whose transactions are invalid is rejected regardless of
whether its Merkle root looks valid.

## Difficulty as leading zero bits

`difficulty` is the number of leading zero BITS that `sha256(serialize_header)`
must have.  For example, difficulty 8 means the hash must start with at least
one zero nibble (`0x00..` to `0x07..`), giving roughly a 1/256 chance per
nonce.  Difficulty is kept low (8–12 bits) in Phase 1 so demos mine in
milliseconds on a CPU.

## Why is the genesis block pinned?

Every node must start from exactly the same first block, otherwise they would
immediately disagree about the chain.  The genesis timestamp, difficulty, payout
public key, and nonce are all hardcoded.  Changing any of them changes the
genesis hash, which would split the network.  The test suite asserts that the
canonical genesis hash matches the hardcoded value.

## Determinism

All hashing and serialization is deterministic: the same inputs always produce
the same bytes and the same hash.  There are no floats, no dictionaries with
unstable iteration order, and no platform-dependent behaviour in consensus code.

## Chain state is derived, not stored

The UTXO set at block N is never written to disk as a snapshot.  It is
recomputed by replaying blocks 1..N from genesis, applying each block's
transactions in order.  Persistence stores only blocks; the in-memory UTXO set is
a cache that is rebuilt whenever the chain tip changes.  This makes the state
unforgeable — any stored state would have to be re-derived and checked anyway, so
deriving it from the block log is the single source of truth.

## What is a reorg?

When two miners build on the same parent, the chain temporarily forks.  Kwartel
resolves forks with the longest-chain rule: the valid chain with the most blocks
wins.  If a competing fork grows longer than the current tip, the node performs a
reorg — it discards the shorter chain's tip blocks and rebuilds the UTXO set by
replaying the longer chain from genesis.  Transactions that only existed on the
losing fork disappear from the tip state.

## Why does coinbase maturity exist?

`COINBASE_MATURITY = 1` means a coinbase output cannot be spent until one block
after it is mined.  This prevents a miner from spending reward output that could
still be orphaned by a reorg, and prevents a coinbase from being spent in the
same block that created it.

## Why must the first transaction be the coinbase?

The coinbase is the only transaction allowed to mint new value (the block reward
plus fees).  Requiring it to be the first transaction, and the only coinbase,
gives validators a fixed, unambiguous place to check the reward equation without
scanning for it.  This also simplifies fee accounting: the coinbase's declared
value must equal `BLOCK_REWARD + sum(all other tx fees)`.

## Coinbase outpoint namespacing

Coinbase txids can collide across blocks (same reward, same payout key, zero
fees).  To keep every coinbase output uniquely spendable without modifying the
transaction dataclasses, coinbase outputs are keyed in the UTXO set by
`block_hash || txid`.  The block hash is unique, so coinbase outpoints never
collide.

