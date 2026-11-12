"""SQLite persistence for Kwartel blocks."""

from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path

from kwartel.blockchain.block import Block, BlockHeader, block_hash, serialize_header
from kwartel.transaction.model import Outpoint, Transaction, TxInput, TxOutput, serialize_tx, txid

_U32 = struct.Struct("<I")
_U64 = struct.Struct("<Q")


def _read_u32(data: bytes, off: int) -> tuple[int, int]:
    return _U32.unpack_from(data, off)[0], off + 4


def _read_u64(data: bytes, off: int) -> tuple[int, int]:
    return _U64.unpack_from(data, off)[0], off + 8


def _read_bytes(data: bytes, off: int) -> tuple[bytes, int]:
    length, off = _read_u32(data, off)
    return data[off : off + length], off + length


def deserialize_tx(data: bytes, off: int) -> tuple[Transaction, int]:
    """Parse one ``serialize_tx`` transaction from ``data`` at ``off``."""
    count_bytes, off = _read_bytes(data, off)
    input_count = _U32.unpack(count_bytes)[0]
    inputs: list[TxInput] = []
    for _ in range(input_count):
        txid_bytes, off = _read_bytes(data, off)
        index_bytes, off = _read_bytes(data, off)
        index = _U32.unpack(index_bytes)[0]
        pubkey, off = _read_bytes(data, off)
        signature, off = _read_bytes(data, off)
        inputs.append(
            TxInput(
                outpoint=Outpoint(txid=txid_bytes.hex(), index=index),
                unlock_pubkey=pubkey,
                signature=signature,
            )
        )

    count_bytes, off = _read_bytes(data, off)
    output_count = _U32.unpack(count_bytes)[0]
    outputs: list[TxOutput] = []
    for _ in range(output_count):
        value_bytes, off = _read_bytes(data, off)
        value = _U64.unpack(value_bytes)[0]
        lock, off = _read_bytes(data, off)
        outputs.append(TxOutput(value=value, lock=lock))

    return Transaction(inputs=tuple(inputs), outputs=tuple(outputs)), off


def serialize_block(block: Block) -> bytes:
    """Return the canonical serialization of ``block`` for storage."""
    data = serialize_header(block.header)
    data += _U32.pack(len(block.transactions))
    for tx in block.transactions:
        data += serialize_tx(tx, include_signatures=True)
    return data


def deserialize_block(data: bytes) -> Block:
    """Reconstruct a ``Block`` from ``serialize_block`` output."""
    off = 0
    prev, off = _read_bytes(data, off)
    merkle, off = _read_bytes(data, off)
    timestamp, off = _read_u64(data, off)
    difficulty, off = _read_u32(data, off)
    nonce, off = _read_u64(data, off)
    header = BlockHeader(
        prev_block_hash=prev.hex(),
        merkle_root=merkle.hex(),
        timestamp=timestamp,
        difficulty=difficulty,
        nonce=nonce,
    )
    tx_count, off = _read_u32(data, off)
    txs: list[Transaction] = []
    for _ in range(tx_count):
        tx, off = deserialize_tx(data, off)
        txs.append(tx)
    return Block(header=header, transactions=tuple(txs))



class BlockStore:
    """SQLite-backed store of blocks plus chain tips."""

    def __init__(self, db_path: str | Path) -> None:
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS blocks (
                hash TEXT PRIMARY KEY,
                height INTEGER NOT NULL,
                prev_block_hash TEXT NOT NULL,
                payload BLOB NOT NULL,
                txids TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_blocks_height ON blocks(height);
            CREATE INDEX IF NOT EXISTS idx_blocks_prev ON blocks(prev_block_hash);
            CREATE TABLE IF NOT EXISTS tips (
                hash TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- reads ---------------------------------------------------------------

    def has_block(self, hash_str: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM blocks WHERE hash = ?", (hash_str,)
        ).fetchone()
        return row is not None

    def get_block(self, hash_str: str) -> Block | None:
        row = self._conn.execute(
            "SELECT payload FROM blocks WHERE hash = ?", (hash_str,)
        ).fetchone()
        if row is None:
            return None
        return deserialize_block(row[0])

    def get_block_height(self, hash_str: str) -> int | None:
        row = self._conn.execute(
            "SELECT height FROM blocks WHERE hash = ?", (hash_str,)
        ).fetchone()
        return row[0] if row is not None else None

    def _best_chain(self) -> list[str]:
        """Return block hashes from genesis to the best tip, in order."""
        tip = self.best_tip_hash
        if tip is None:
            return []
        hashes: list[str] = []
        cur = tip
        while True:
            block = self.get_block(cur)
            if block is None:
                break
            hashes.append(cur)
            if block.header.prev_block_hash == "00" * 32:
                break
            cur = block.header.prev_block_hash
        hashes.reverse()
        return hashes

    def get_block_by_height(self, height: int) -> Block | None:
        chain = self._best_chain()
        if height < 0 or height >= len(chain):
            return None
        return self.get_block(chain[height])

    def iter_blocks_from_height(self, h: int):
        chain = self._best_chain()
        for hash_str in chain[h:]:
            block = self.get_block(hash_str)
            if block is not None:
                yield block

    def height(self) -> int:
        chain = self._best_chain()
        return len(chain) - 1

    @property
    def tips(self) -> set[str]:
        rows = self._conn.execute("SELECT hash FROM tips").fetchall()
        return {r[0] for r in rows}

    @property
    def best_tip_hash(self) -> str | None:
        row = self._conn.execute(
            "SELECT t.hash FROM tips t JOIN blocks b ON t.hash = b.hash "
            "ORDER BY b.height DESC, t.hash ASC LIMIT 1"
        ).fetchone()
        return row[0] if row is not None else None

    # -- writes --------------------------------------------------------------

    def save_block(self, block: Block) -> None:
        hash_str = block_hash(block.header)
        if self.has_block(hash_str):
            return

        prev = block.header.prev_block_hash
        if prev == "00" * 32:
            height = 0
        else:
            parent_height = self.get_block_height(prev)
            if parent_height is None:
                raise ValueError("cannot save block with unknown parent")
            height = parent_height + 1

        txids_json = json.dumps([txid(tx) for tx in block.transactions])
        self._conn.execute(
            "INSERT INTO blocks (hash, height, prev_block_hash, payload, txids) "
            "VALUES (?, ?, ?, ?, ?)",
            (hash_str, height, prev, serialize_block(block), txids_json),
        )
        self._conn.execute("DELETE FROM tips WHERE hash = ?", (prev,))
        self._conn.execute("INSERT OR IGNORE INTO tips (hash) VALUES (?)", (hash_str,))
        self._conn.commit()
