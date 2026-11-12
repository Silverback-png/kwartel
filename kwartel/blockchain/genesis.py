"""Genesis block construction for Kwartel."""

from __future__ import annotations

from kwartel.blockchain.block import Block, BlockHeader
from kwartel.blockchain.merkle import merkle_root
from kwartel.transaction.model import KWARTS_PER_KWT, Transaction, TxOutput, txid

GENESIS_TIMESTAMP = 1757200000
GENESIS_DIFFICULTY = 8
GENESIS_PREV_HASH = "00" * 32

# Canonical dev pubkey for the pinned genesis block.  Only the public key is
# stored; the secret key is discarded.
GENESIS_DEV_PUBLIC_KEY = bytes.fromhex(
    "aab172f433f770babfed8ac9c4b83d5926ae850822bfa7846bc1e1e1731ae965"
)

GENESIS_PAYOUT = TxOutput(
    value=100 * KWARTS_PER_KWT,
    lock=GENESIS_DEV_PUBLIC_KEY,
)

# Mined once and hardcoded to pin consensus.
GENESIS_NONCE = 244
GENESIS_HASH = "00672dafecdc4b0708dddcbb82337a713f209858083d129ac0e3d5349054694f"


def create_genesis_block(payout: TxOutput) -> Block:
    """Return the chain's first block with the given coinbase payout."""
    coinbase = Transaction(inputs=(), outputs=(payout,))
    transactions = (coinbase,)
    root = merkle_root([txid(coinbase)])
    header = BlockHeader(
        prev_block_hash=GENESIS_PREV_HASH,
        merkle_root=root,
        timestamp=GENESIS_TIMESTAMP,
        difficulty=GENESIS_DIFFICULTY,
        nonce=GENESIS_NONCE,
    )
    return Block(header=header, transactions=transactions)
