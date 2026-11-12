"""Demo script for kwartel.blockchain."""

from __future__ import annotations

import time
from pathlib import Path

from kwartel.blockchain.block import (
    Block,
    BlockHeader,
    block_hash,
    leading_zero_bits,
    meets_difficulty,
    mine_block,
)
from kwartel.blockchain.genesis import GENESIS_HASH, GENESIS_TIMESTAMP, create_genesis_block
from kwartel.blockchain.chain import Chain
from kwartel.blockchain.coinbase import BLOCK_REWARD, coinbase_outpoint, create_coinbase
from kwartel.blockchain.persistence import BlockStore
from kwartel.blockchain.merkle import merkle_root
from kwartel.crypto.keys import address, generate_keypair
from kwartel.transaction.model import (
    KWARTS_PER_KWT,
    Outpoint,
    Transaction,
    TxOutput,
    txid,
)
from kwartel.transaction.utxo_set import UTXOSet
from kwartel.transaction.validation import validate_tx


def _kwt_str(kwarts: int) -> str:
    """Return a human-readable KWT string without using float."""
    return f"{kwarts // KWARTS_PER_KWT} KWT ({kwarts} kwarts)"


def demo_task03() -> None:
    dev = generate_keypair()
    bob = generate_keypair()
    charlie = generate_keypair()
    dave = generate_keypair()

    print("Addresses (no secret keys shown):")
    print(f"  Dev:    {address(dev.public)}")
    print(f"  Bob:    {address(bob.public)}")
    print(f"  Charlie: {address(charlie.public)}")
    print(f"  Dave:   {address(dave.public)}")
    print()

    # Genesis block: premine the dev address.
    genesis_payout = TxOutput(value=100 * KWARTS_PER_KWT, lock=dev.public)
    genesis = create_genesis_block(genesis_payout)
    genesis_mined_header = mine_block(genesis.header)
    genesis = Block(header=genesis_mined_header, transactions=genesis.transactions)
    genesis_hash = block_hash(genesis.header)
    print(f"Genesis block hash: {genesis_hash}")
    print(f"Genesis nonce:      {genesis.header.nonce}")
    print(f"Genesis leading zero bits: {leading_zero_bits(genesis_hash)}")
    print()

    # Seed the UTXO set with the genesis coinbase output.
    utxo = UTXOSet()
    genesis_txid = txid(genesis.transactions[0])
    utxo.add_output(Outpoint(txid=genesis_txid, index=0), genesis_payout)

    # Build three signed transactions spending the premine (chained via change).
    tx1 = Transaction.create(
        inputs_to_spend={Outpoint(txid=genesis_txid, index=0): genesis_payout},
        recipients=[(30 * KWARTS_PER_KWT, bob.public)],
        signer=dev,
        change_pubkey=dev.public,
    )
    tx1_id = txid(tx1)
    print(f"Tx1 txid: {tx1_id} violations: {validate_tx(tx1, utxo)}")
    utxo.apply_transaction(tx1)

    tx2 = Transaction.create(
        inputs_to_spend={Outpoint(txid=tx1_id, index=1): tx1.outputs[1]},
        recipients=[(20 * KWARTS_PER_KWT, charlie.public)],
        signer=dev,
        change_pubkey=dev.public,
    )
    tx2_id = txid(tx2)
    print(f"Tx2 txid: {tx2_id} violations: {validate_tx(tx2, utxo)}")
    utxo.apply_transaction(tx2)

    tx3 = Transaction.create(
        inputs_to_spend={Outpoint(txid=tx2_id, index=1): tx2.outputs[1]},
        recipients=[(10 * KWARTS_PER_KWT, dave.public)],
        signer=dev,
        change_pubkey=dev.public,
    )
    tx3_id = txid(tx3)
    print(f"Tx3 txid: {tx3_id} violations: {validate_tx(tx3, utxo)}")
    utxo.apply_transaction(tx3)
    print()

    transactions = (tx1, tx2, tx3)
    txids = [txid(tx) for tx in transactions]
    merkle = merkle_root(txids)
    print(f"Merkle root of 3 txs: {merkle}")
    print()

    # Mine a second block committing to these transactions.
    header_template = BlockHeader(
        prev_block_hash=genesis_hash,
        merkle_root=merkle,
        timestamp=int(time.time()),
        difficulty=8,
        nonce=0,
    )
    start = time.perf_counter()
    mined_header = mine_block(header_template)
    elapsed = time.perf_counter() - start
    second_block = Block(header=mined_header, transactions=transactions)
    second_hash = block_hash(mined_header)

    print(f"Second block hash: {second_hash}")
    print(f"Second block merkle root: {merkle}")
    print(f"Second block nonce: {mined_header.nonce}")
    print(f"Mining time: {elapsed:.4f}s")
    print(f"Leading zero bits: {leading_zero_bits(second_hash)}")
    print(f"Meets difficulty: {meets_difficulty(mined_header)}")
    print()

    # Tamper with one transaction and show the cascade.
    tampered_tx1 = Transaction.create(
        inputs_to_spend={Outpoint(txid=genesis_txid, index=0): genesis_payout},
        recipients=[(31 * KWARTS_PER_KWT, bob.public)],  # 1 KWT more to Bob
        signer=dev,
        change_pubkey=dev.public,
    )
    tampered_transactions = (tampered_tx1, tx2, tx3)
    tampered_merkle = merkle_root([txid(tx) for tx in tampered_transactions])
    tampered_header = BlockHeader(
        prev_block_hash=genesis_hash,
        merkle_root=tampered_merkle,
        timestamp=header_template.timestamp,
        difficulty=8,
        nonce=mined_header.nonce,  # same nonce as valid block
    )
    tampered_hash = block_hash(tampered_header)

    print("Tamper demo:")
    print(f"  Original merkle root: {merkle}")
    print(f"  Tampered merkle root: {tampered_merkle}")
    print(f"  Merkle root changed:  {merkle != tampered_merkle}")
    print(f"  Tampered block hash:  {tampered_hash}")
    print(f"  Leading zero bits of tampered block: {leading_zero_bits(tampered_hash)}")
    print(f"  Tampered block meets difficulty: {meets_difficulty(tampered_header)}")


def demo_chain() -> None:
    """Mine a small chain, demonstrate a reorg, and prove restart survival."""
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / "kwartel_chain.db"
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()

    chain = Chain(BlockStore(db_path))
    miner = generate_keypair()
    alice = generate_keypair()

    print("=" * 62)
    print("Chain demo (persistence + fork choice)")
    print(f"  Miner: {address(miner.public)}")
    print(f"  Alice: {address(alice.public)}")
    print(f"  Genesis: height {chain.height()} hash {block_hash(chain.tip().header)[:16]}...")
    print()

    def build(prev_hash, miner_pubkey, txs, timestamp):
        cb = create_coinbase(0, miner_pubkey, 0)
        block_txs = (cb,) + tuple(txs)
        header = BlockHeader(
            prev_block_hash=prev_hash,
            merkle_root=merkle_root([txid(t) for t in block_txs]),
            timestamp=timestamp,
            difficulty=8,
            nonce=0,
        )
        return Block(mine_block(header), block_txs)

    # Phase 1: mine genesis + 4 blocks, spending matured coinbase rewards.
    ts = GENESIS_TIMESTAMP
    for i in range(1, 5):
        txs = []
        if i >= 2:
            prev = chain.tip()
            prev_cb = prev.transactions[0]
            cbo = coinbase_outpoint(block_hash(prev.header), txid(prev_cb))
            spend = Transaction.create(
                inputs_to_spend={cbo: TxOutput(value=BLOCK_REWARD, lock=miner.public)},
                recipients=[(BLOCK_REWARD, alice.public)],
                signer=miner,
                change_pubkey=miner.public,
            )
            txs.append(spend)
        ts += 1
        block = build(block_hash(chain.tip().header), miner.public, txs, ts)
        res = chain.add_block(block)
        print(
            f"  block {i}: add={res} height={chain.height()} "
            f"tip={block_hash(chain.tip().header)[:16]}... "
            f"miner={chain.balance(miner.public)} alice={chain.balance(alice.public)}"
        )
    print()

    # Phase 2: a 5-block fork from genesis overtakes the 4-block chain.
    fork_miner = generate_keypair()
    prev_hash = GENESIS_HASH
    ts = GENESIS_TIMESTAMP
    for _ in range(5):
        ts += 1
        block = build(prev_hash, fork_miner.public, (), ts)
        assert chain.add_block(block) == []
        prev_hash = block_hash(block.header)
    print("After 5-block fork overtakes:")
    print(f"  height={chain.height()} tip={block_hash(chain.tip().header)[:16]}...")
    print(f"  old miner balance: {chain.balance(miner.public)}")
    print(f"  alice balance:     {chain.balance(alice.public)}")
    print(f"  fork miner balance: {chain.balance(fork_miner.public)}")
    print()

    # Phase 3: reopen from disk and confirm state is restored.
    chain2 = Chain(BlockStore(db_path))
    print("Reopened from disk (fresh Chain object):")
    print(f"  height={chain2.height()} tip={block_hash(chain2.tip().header)[:16]}...")
    print(f"  fork miner balance: {chain2.balance(fork_miner.public)}")
    print(f"  alice balance:      {chain2.balance(alice.public)}")


def main() -> None:
    demo_task03()
    print()
    demo_chain()


if __name__ == "__main__":
    main()
