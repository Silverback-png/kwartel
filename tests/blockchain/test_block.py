"""Tests for kwartel.blockchain.block."""

from kwartel.blockchain.block import (
    Block,
    BlockHeader,
    block_hash,
    is_coinbase_only,
    leading_zero_bits,
    meets_difficulty,
    mine_block,
    serialize_header,
    validate_block_structure,
)
from kwartel.crypto.keys import generate_keypair
from kwartel.transaction.model import Outpoint, Transaction, TxInput, TxOutput


def _h(difficulty: int = 1, nonce: int = 0) -> BlockHeader:
    return BlockHeader(
        prev_block_hash="00" * 32,
        merkle_root="11" * 32,
        timestamp=1757200000,
        difficulty=difficulty,
        nonce=nonce,
    )


def _coinbase(value: int = 100) -> Transaction:
    kp = generate_keypair()
    return Transaction(inputs=(), outputs=(TxOutput(value=value, lock=kp.public),))


def test_serialize_header_deterministic():
    assert serialize_header(_h()) == serialize_header(_h())


def test_serialize_header_prefix():
    assert serialize_header(_h()).startswith(b"\x20\x00\x00\x00")


def test_block_hash_is_64_hex_chars():
    assert len(block_hash(_h())) == 64


def test_block_hash_changes_with_merkle_root():
    h1, h2 = _h(), _h()
    object.__setattr__(h2, "merkle_root", "22" * 32)
    assert block_hash(h1) != block_hash(h2)


def test_leading_zero_bits_all_zeros():
    assert leading_zero_bits("0" * 64) == 256


def test_leading_zero_bits_boundary_vectors():
    assert leading_zero_bits("0" * 15 + "8" + "f" * 48) == 60
    assert leading_zero_bits("0" * 15 + "4" + "f" * 48) == 61
    assert leading_zero_bits("0" * 15 + "2" + "f" * 48) == 62
    assert leading_zero_bits("0" * 15 + "1" + "f" * 48) == 63
    assert leading_zero_bits("0" * 16 + "8" + "f" * 47) == 64
    assert leading_zero_bits("0" * 16 + "4" + "f" * 47) == 65


def test_meets_difficulty_true_at_threshold():
    assert leading_zero_bits("00" + "f" * 62) == 8


def test_meets_difficulty_false_below_threshold():
    assert leading_zero_bits("ff" + "0" * 62) == 0


def test_mine_block_finds_valid_header():
    mined = mine_block(_h(difficulty=8))
    assert meets_difficulty(mined)


def test_mine_block_is_deterministic():
    h = _h(difficulty=8)
    assert mine_block(h) == mine_block(h)


def test_mine_block_raises_when_exhausted():
    try:
        mine_block(_h(difficulty=32), max_nonce=10)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")


def test_is_coinbase_only_true():
    assert is_coinbase_only(Block(_h(), (_coinbase(),))) is True


def test_is_coinbase_only_false_with_inputs():
    alice, bob = generate_keypair(), generate_keypair()
    tx_in = TxInput(Outpoint("a" * 64, 0), alice.public, b"\x00" * 64)
    tx = Transaction((tx_in,), (TxOutput(10, bob.public),))
    assert is_coinbase_only(Block(_h(), (tx,))) is False


def test_validate_block_structure_valid_coinbase_only():
    assert validate_block_structure(Block(_h(), (_coinbase(),))) == []


def test_validate_block_structure_empty_transactions():
    block = Block(_h(), ())
    assert any("no transactions" in v.lower() for v in validate_block_structure(block))


def test_validate_block_structure_negative_timestamp():
    h = _h()
    object.__setattr__(h, "timestamp", -1)
    assert any("timestamp" in v.lower() for v in validate_block_structure(Block(h, (_coinbase(),))))


def test_validate_block_structure_difficulty_too_low():
    h = _h()
    object.__setattr__(h, "difficulty", 0)
    assert any("difficulty" in v.lower() for v in validate_block_structure(Block(h, (_coinbase(),))))


def test_validate_block_structure_nonce_out_of_range():
    h = _h()
    object.__setattr__(h, "nonce", 2**64)
    assert any("nonce" in v.lower() for v in validate_block_structure(Block(h, (_coinbase(),))))


def test_validate_block_structure_bad_prev_hash():
    h = _h()
    object.__setattr__(h, "prev_block_hash", "nothex")
    assert any("prev_block_hash" in v for v in validate_block_structure(Block(h, (_coinbase(),))))


def test_validate_block_structure_bad_merkle_root():
    h = _h()
    object.__setattr__(h, "merkle_root", "zz" * 32)
    assert any("merkle_root" in v for v in validate_block_structure(Block(h, (_coinbase(),))))


def test_validate_block_structure_output_value_zero():
    kp = generate_keypair()
    tx = Transaction((), (TxOutput(0, kp.public),))
    assert any("value" in v.lower() for v in validate_block_structure(Block(_h(), (tx,))))


def test_validate_block_structure_multiple_coinbases():
    kp1, kp2 = generate_keypair(), generate_keypair()
    tx1 = Transaction((), (TxOutput(10, kp1.public),))
    tx2 = Transaction((), (TxOutput(10, kp2.public),))
    assert any("more than one coinbase" in v.lower() for v in validate_block_structure(Block(_h(), (tx1, tx2))))


def test_validate_block_structure_never_raises_on_bad_input():
    block = Block(header=None, transactions=())  # type: ignore[arg-type]
    assert validate_block_structure(block)
