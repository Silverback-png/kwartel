"""Tests for kwartel.blockchain.chain."""

from kwartel.blockchain.block import Block, BlockHeader, block_hash, mine_block
from kwartel.blockchain.chain import Chain
from kwartel.blockchain.coinbase import BLOCK_REWARD, coinbase_outpoint, create_coinbase
from kwartel.blockchain.genesis import GENESIS_HASH
from kwartel.blockchain.merkle import merkle_root
from kwartel.blockchain.persistence import BlockStore
from kwartel.crypto.keys import generate_keypair
from kwartel.transaction.model import Outpoint, Transaction, TxInput, TxOutput, txid

TS0 = 1757200000


def _mine(prev_hash, txs, timestamp):
    header = BlockHeader(prev_hash, merkle_root([txid(t) for t in txs]), timestamp, 8, 0)
    return Block(mine_block(header), tuple(txs))


def _cb_only(prev_hash, miner, timestamp):
    return _mine(prev_hash, (create_coinbase(0, miner.public, 0),), timestamp)


def _spend(cbo, value, signer, recipient_pubkey):
    return Transaction.create(
        inputs_to_spend={cbo: TxOutput(value=value, lock=signer.public)},
        recipients=[(value, recipient_pubkey)],
        signer=signer,
        change_pubkey=signer.public,
    )


def _new_chain(tmp_path):
    return Chain(BlockStore(tmp_path / "chain.db"))


def test_genesis_initialized(tmp_path):
    chain = _new_chain(tmp_path)
    assert chain.height() == 0
    assert block_hash(chain.tip().header) == GENESIS_HASH


def test_add_valid_block(tmp_path):
    chain = _new_chain(tmp_path)
    miner = generate_keypair()
    block1 = _cb_only(block_hash(chain.tip().header), miner, TS0 + 1)
    assert chain.add_block(block1) == []
    assert chain.height() == 1
    assert block_hash(chain.tip().header) == block_hash(block1.header)


def test_unknown_parent(tmp_path):
    chain = _new_chain(tmp_path)
    block = _cb_only("ff" * 32, generate_keypair(), TS0 + 1)
    assert any("parent" in v.lower() for v in chain.add_block(block))


def test_bad_merkle_root(tmp_path):
    chain = _new_chain(tmp_path)
    miner = generate_keypair()
    cb = create_coinbase(0, miner.public, 0)
    header = BlockHeader(block_hash(chain.tip().header), "00" * 32, TS0 + 1, 8, 0)
    block = Block(mine_block(header), (cb,))
    assert any("merkle" in v.lower() for v in chain.add_block(block))


def test_coinbase_not_first(tmp_path):
    chain = _new_chain(tmp_path)
    alice, bob = generate_keypair(), generate_keypair()
    non_cb = Transaction((TxInput(Outpoint("a" * 64, 0), alice.public, b"\x00" * 64),), (TxOutput(1, bob.public),))
    cb = create_coinbase(0, alice.public, 0)
    header = BlockHeader(block_hash(chain.tip().header), merkle_root([txid(non_cb), txid(cb)]), TS0 + 1, 8, 0)
    block = Block(mine_block(header), (non_cb, cb))
    assert any("first transaction" in v.lower() for v in chain.add_block(block))


def test_bad_coinbase_reward(tmp_path):
    chain = _new_chain(tmp_path)
    miner = generate_keypair()
    cb = create_coinbase(0, miner.public, 0)
    object.__setattr__(cb.outputs[0], "value", BLOCK_REWARD - 1)
    header = BlockHeader(block_hash(chain.tip().header), merkle_root([txid(cb)]), TS0 + 1, 8, 0)
    block = Block(mine_block(header), (cb,))
    assert any("value" in v.lower() for v in chain.add_block(block))


def test_bad_difficulty(tmp_path):
    chain = _new_chain(tmp_path)
    miner = generate_keypair()
    cb = create_coinbase(0, miner.public, 0)
    header = BlockHeader(block_hash(chain.tip().header), merkle_root([txid(cb)]), TS0 + 1, 32, 0)
    block = Block(header, (cb,))
    assert any("difficulty" in v.lower() for v in chain.add_block(block))


def test_spend_matured_coinbase(tmp_path):
    chain = _new_chain(tmp_path)
    miner, alice = generate_keypair(), generate_keypair()
    block1 = _cb_only(block_hash(chain.tip().header), miner, TS0 + 1)
    assert chain.add_block(block1) == []
    b1h = block_hash(block1.header)
    cbo = coinbase_outpoint(b1h, txid(block1.transactions[0]))
    spend = _spend(cbo, BLOCK_REWARD, miner, alice.public)
    block2 = _mine(b1h, (create_coinbase(0, miner.public, 0), spend), TS0 + 2)
    assert chain.add_block(block2) == []
    assert chain.balance(alice.public) == BLOCK_REWARD


def test_invalid_tx_rejected(tmp_path):
    chain = _new_chain(tmp_path)
    miner, bob = generate_keypair(), generate_keypair()
    block1 = _cb_only(block_hash(chain.tip().header), miner, TS0 + 1)
    assert chain.add_block(block1) == []
    bad = Transaction((TxInput(Outpoint("f" * 64, 0), miner.public, b"\x00" * 64),), (TxOutput(10, bob.public),))
    block2 = _mine(block_hash(block1.header), (create_coinbase(0, miner.public, 0), bad), TS0 + 2)
    assert any("invalid" in v.lower() for v in chain.add_block(block2))


def test_timestamp_not_monotonic(tmp_path):
    chain = _new_chain(tmp_path)
    miner = generate_keypair()
    block1 = _cb_only(block_hash(chain.tip().header), miner, TS0 + 1)
    assert chain.add_block(block1) == []
    block2 = _cb_only(block_hash(block1.header), miner, TS0 + 1)
    assert any("timestamp" in v.lower() for v in chain.add_block(block2))


def test_reorg_longer_fork_adopted(tmp_path):
    chain = _new_chain(tmp_path)
    miner_a, miner_b, alice = generate_keypair(), generate_keypair(), generate_keypair()
    genesis_hash = block_hash(chain.tip().header)

    a1 = _cb_only(genesis_hash, miner_a, TS0 + 1)
    assert chain.add_block(a1) == []
    a1h = block_hash(a1.header)
    spend = _spend(coinbase_outpoint(a1h, txid(a1.transactions[0])), BLOCK_REWARD, miner_a, alice.public)
    a2 = _mine(a1h, (create_coinbase(0, miner_a.public, 0), spend), TS0 + 2)
    assert chain.add_block(a2) == []
    assert chain.height() == 2
    assert chain.balance(alice.public) == BLOCK_REWARD

    b1 = _cb_only(genesis_hash, miner_b, TS0 + 1)
    assert chain.add_block(b1) == []
    b2 = _cb_only(block_hash(b1.header), miner_b, TS0 + 2)
    assert chain.add_block(b2) == []
    b3 = _cb_only(block_hash(b2.header), miner_b, TS0 + 3)
    assert chain.add_block(b3) == []

    assert chain.height() == 3
    assert block_hash(chain.tip().header) == block_hash(b3.header)
    assert chain.balance(alice.public) == 0


def test_shorter_fork_not_adopted(tmp_path):
    chain = _new_chain(tmp_path)
    miner_a, miner_b, alice = generate_keypair(), generate_keypair(), generate_keypair()
    genesis_hash = block_hash(chain.tip().header)

    a1 = _cb_only(genesis_hash, miner_a, TS0 + 1)
    assert chain.add_block(a1) == []
    a1h = block_hash(a1.header)
    spend = _spend(coinbase_outpoint(a1h, txid(a1.transactions[0])), BLOCK_REWARD, miner_a, alice.public)
    a2 = _mine(a1h, (create_coinbase(0, miner_a.public, 0), spend), TS0 + 2)
    assert chain.add_block(a2) == []

    b1 = _cb_only(genesis_hash, miner_b, TS0 + 1)
    assert chain.add_block(b1) == []

    assert chain.height() == 2
    assert block_hash(chain.tip().header) == block_hash(a2.header)
    assert chain.balance(alice.public) == BLOCK_REWARD


def test_restart_reproduces_state(tmp_path):
    db = tmp_path / "chain.db"
    miner = generate_keypair()
    chain = Chain(BlockStore(db))
    block1 = _cb_only(block_hash(chain.tip().header), miner, TS0 + 1)
    assert chain.add_block(block1) == []
    block2 = _cb_only(block_hash(block1.header), miner, TS0 + 2)
    assert chain.add_block(block2) == []

    height = chain.height()
    tip_hash = block_hash(chain.tip().header)
    balance = chain.balance(miner.public)

    chain2 = Chain(BlockStore(db))
    assert chain2.height() == height
    assert block_hash(chain2.tip().header) == tip_hash
    assert chain2.balance(miner.public) == balance

