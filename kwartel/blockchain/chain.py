"""Blockchain: storage, full validation, and longest-chain fork choice."""

from __future__ import annotations

from kwartel.blockchain.block import Block, block_hash, meets_difficulty, validate_block_structure
from kwartel.blockchain.coinbase import COINBASE_MATURITY, coinbase_outpoint, validate_coinbase
from kwartel.blockchain.genesis import GENESIS_PAYOUT, create_genesis_block
from kwartel.blockchain.merkle import merkle_root
from kwartel.blockchain.persistence import BlockStore
from kwartel.transaction.model import Outpoint, txid
from kwartel.transaction.utxo_set import UTXOSet
from kwartel.transaction.validation import is_coinbase, validate_tx


class Chain:
    """The Kwartel blockchain: append-only blocks, validation, and fork choice."""

    def __init__(self, store: BlockStore) -> None:
        self._store = store
        if store.height() < 0:
            store.save_block(create_genesis_block(GENESIS_PAYOUT))
        best = store.best_tip_hash
        assert best is not None
        self._tip = store.get_block(best)
        self._tip_height = store.get_block_height(best) or 0
        self._utxo_cache, self._coinbase_heights = self._replay(best)

    # -- public API ---------------------------------------------------------

    def add_block(self, block: Block) -> list[str]:
        """Validate and append ``block``. Returns [] on success, violations otherwise."""
        violations = validate_block_structure(block)
        if violations:
            return violations

        header = block.header

        if not self._store.has_block(header.prev_block_hash):
            return [f"parent block not found: {header.prev_block_hash}"]

        if not meets_difficulty(header):
            return [f"header hash does not meet difficulty {header.difficulty}"]

        if header.merkle_root != merkle_root([txid(tx) for tx in block.transactions]):
            return ["merkle root does not match block transactions"]

        if not block.transactions or not is_coinbase(block.transactions[0]):
            return ["first transaction must be the coinbase"]

        parent_utxo, parent_heights = self._state_at(header.prev_block_hash)
        new_height = (self._store.get_block_height(header.prev_block_hash) or 0) + 1
        new_hash = block_hash(header)

        coinbase = block.transactions[0]
        cbo = coinbase_outpoint(new_hash, txid(coinbase))
        working = parent_utxo.copy()
        heights = dict(parent_heights)
        working.add_output(cbo, coinbase.outputs[0])
        heights[cbo] = new_height

        total_fees = 0
        for tx in block.transactions[1:]:
            for tx_in in tx.inputs:
                op = tx_in.outpoint
                if op in heights and new_height - heights[op] < COINBASE_MATURITY:
                    return [f"coinbase output spent before maturity: {op}"]
            tv = validate_tx(tx, working)
            if tv:
                return [f"transaction {txid(tx)} invalid: " + "; ".join(tv)]
            total_in = sum(working[tx_in.outpoint].value for tx_in in tx.inputs)
            total_out = sum(o.value for o in tx.outputs)
            total_fees += total_in - total_out
            working.apply_transaction(tx)

        cv = validate_coinbase(coinbase, block, total_fees)
        if cv:
            return cv

        parent_block = self._store.get_block(header.prev_block_hash)
        if header.timestamp <= parent_block.header.timestamp:
            return ["block timestamp must be greater than parent timestamp"]

        self._store.save_block(block)
        best = self._store.best_tip_hash
        if best is not None and best != self._tip_hash():
            self._set_tip(best)
        return []

    def tip(self) -> Block:
        return self._tip

    def height(self) -> int:
        return self._tip_height

    def balance(self, pubkey: bytes) -> int:
        return self._utxo_cache.balance(pubkey)

    def utxo_set(self) -> UTXOSet:
        return self._utxo_cache

    # -- internals ----------------------------------------------------------

    def _tip_hash(self) -> str:
        return block_hash(self._tip.header)

    def _state_at(self, block_hash: str) -> tuple[UTXOSet, dict[Outpoint, int]]:
        if block_hash == self._tip_hash():
            return self._utxo_cache.copy(), dict(self._coinbase_heights)
        return self._replay(block_hash)

    def _replay(self, tip_hash: str) -> tuple[UTXOSet, dict[Outpoint, int]]:
        utxo = UTXOSet()
        heights: dict[Outpoint, int] = {}
        for height, h in enumerate(self._chain_to(tip_hash)):
            block = self._store.get_block(h)
            coinbase = block.transactions[0]
            cbo = coinbase_outpoint(h, txid(coinbase))
            utxo.add_output(cbo, coinbase.outputs[0])
            heights[cbo] = height
            for tx in block.transactions[1:]:
                utxo.apply_transaction(tx)
        return utxo, heights

    def _chain_to(self, tip_hash: str) -> list[str]:
        hashes: list[str] = []
        cur = tip_hash
        while True:
            block = self._store.get_block(cur)
            if block is None:
                break
            hashes.append(cur)
            if block.header.prev_block_hash == "00" * 32:
                break
            cur = block.header.prev_block_hash
        hashes.reverse()
        return hashes

    def _set_tip(self, tip_hash: str) -> None:
        self._utxo_cache, self._coinbase_heights = self._replay(tip_hash)
        self._tip = self._store.get_block(tip_hash)
        self._tip_height = self._store.get_block_height(tip_hash) or 0
