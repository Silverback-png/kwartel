"""Tests for kwartel.blockchain.persistence."""

from kwartel.blockchain.block import Block, BlockHeader, block_hash, mine_block
from kwartel.blockchain.coinbase import create_coinbase
from kwartel.blockchain.merkle import merkle_root
from kwartel.blockchain.persistence import BlockStore, deserialize_block, serialize_block
from kwartel.crypto.keys import generate_keypair
from kwartel.transaction.model import KWARTS_PER_KWT, Outpoint, Transaction, TxOutput, txid


def _block(prev_hash: str, txs: tuple, timestamp: int) -> Block:
    header = BlockHeader(
        prev_block_hash=prev_hash,
        merkle_root=merkle_root([txid(t) for t in txs]),
        timestamp=timestamp,
        difficulty=8,
        nonce=0,
    )
    mined = mine_block(header)
    return Block(header=mined, transactions=txs)


def _coinbase_only(prev_hash: str, pubkey: bytes, timestamp: int) -> Block:
    cb = create_coinbase(0, pubkey, 0)
    return _block(prev_hash, (cb,), timestamp)


def test_roundtrip_coinbase_block():
    kp = generate_keypair()
    block = _coinbase_only("00" * 32, kp.public, 1757200000)
    restored = deserialize_block(serialize_block(block))
    assert restored == block
    assert block_hash(restored.header) == block_hash(block.header)


def test_roundtrip_block_with_signed_tx():
    alice = generate_keypair()
    bob = generate_keypair()
    genesis = _coinbase_only("00" * 32, alice.public, 1757200000)
    # spend the genesis coinbase
    cbo = Outpoint(txid=txid(genesis.transactions[0]), index=0)
    spend = Transaction.create(
        inputs_to_spend={cbo: TxOutput(value=50 * KWARTS_PER_KWT, lock=alice.public)},
        recipients=[(50 * KWARTS_PER_KWT, bob.public)],
        signer=alice,
        change_pubkey=alice.public,
    )
    block = _block(block_hash(genesis.header), (spend,), 1757200001)
    restored = deserialize_block(serialize_block(block))
    assert restored == block
    assert [txid(t) for t in restored.transactions] == [txid(t) for t in block.transactions]


def test_save_get_and_has(tmp_path):
    store = BlockStore(tmp_path / "test.db")
    kp = generate_keypair()
    block = _coinbase_only("00" * 32, kp.public, 1757200000)
    store.save_block(block)
    h = block_hash(block.header)
    assert store.has_block(h) is True
    assert store.get_block(h) == block


def test_height_and_get_by_height(tmp_path):
    store = BlockStore(tmp_path / "test.db")
    kp = generate_keypair()
    genesis = _coinbase_only("00" * 32, kp.public, 1757200000)
    store.save_block(genesis)
    assert store.height() == 0
    assert store.get_block_by_height(0) == genesis


def test_ten_blocks_roundtrip(tmp_path):
    store = BlockStore(tmp_path / "test.db")
    kp = generate_keypair()
    prev = "00" * 32
    for i in range(10):
        block = _coinbase_only(prev, kp.public, 1757200000 + i)
        store.save_block(block)
        prev = block_hash(block.header)
    assert store.height() == 9
    blocks = list(store.iter_blocks_from_height(0))
    assert len(blocks) == 10


def test_reopen_persists(tmp_path):
    db = tmp_path / "test.db"
    kp = generate_keypair()
    block = _coinbase_only("00" * 32, kp.public, 1757200000)
    store = BlockStore(db)
    store.save_block(block)
    store.close()

    store2 = BlockStore(db)
    h = block_hash(block.header)
    assert store2.has_block(h) is True
    assert store2.get_block(h) == block
    store2.close()


def test_tips_tracking(tmp_path):
    store = BlockStore(tmp_path / "test.db")
    kp = generate_keypair()
    genesis = _coinbase_only("00" * 32, kp.public, 1757200000)
    store.save_block(genesis)
    assert store.tips == {block_hash(genesis.header)}
