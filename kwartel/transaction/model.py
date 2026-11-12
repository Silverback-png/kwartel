"""UTXO transaction model for Kwartel."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from kwartel.crypto.keys import KeyPair, hash_bytes, sha256_hex, sign

KWARTS_PER_KWT = 100_000_000


@dataclass(frozen=True)
class Outpoint:
    """Reference to a specific output of a previous transaction."""

    txid: str
    index: int


@dataclass(frozen=True)
class TxOutput:
    """A transaction output: a value locked to a public key."""

    value: int
    lock: bytes

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("TxOutput value cannot be negative")
        if len(self.lock) != 32:
            raise ValueError("TxOutput lock must be a 32-byte public key")


@dataclass(frozen=True)
class TxInput:
    """A transaction input: consumes an outpoint and provides a signature."""

    outpoint: Outpoint
    unlock_pubkey: bytes
    signature: bytes


@dataclass(frozen=True)
class Transaction:
    """A UTXO transaction: inputs consumed and outputs created."""

    inputs: tuple[TxInput, ...]
    outputs: tuple[TxOutput, ...]

    @classmethod
    def create(
        cls,
        inputs_to_spend: dict[Outpoint, TxOutput],
        recipients: list[tuple[int, bytes]],
        signer: KeyPair,
        change_pubkey: bytes | None = None,
    ) -> Transaction:
        """Build and sign a transaction spending the given inputs.

        Args:
            inputs_to_spend: mapping of outpoints to outputs the signer owns.
            recipients: list of ``(value_in_kwarts, recipient_pubkey)`` pairs.
            signer: the keypair that owns the inputs being spent.
            change_pubkey: optional pubkey to receive change.

        Returns:
            A fully signed ``Transaction``.
        """
        total_in = 0
        unsigned_inputs: list[TxInput] = []
        for outpoint, output in inputs_to_spend.items():
            if output.lock != signer.public:
                raise ValueError("input is not locked to signer")
            total_in += output.value
            unsigned_inputs.append(
                TxInput(
                    outpoint=outpoint,
                    unlock_pubkey=signer.public,
                    signature=b"",
                )
            )

        total_out = sum(value for value, _pubkey in recipients)
        if total_out > total_in:
            raise ValueError("insufficient funds")

        change = total_in - total_out
        outputs: list[TxOutput] = []
        for value, pubkey in recipients:
            outputs.append(TxOutput(value=value, lock=pubkey))
        if change > 0:
            if change_pubkey is None:
                raise ValueError("change due but no change pubkey provided")
            outputs.append(TxOutput(value=change, lock=change_pubkey))

        unsigned_tx = cls(inputs=tuple(unsigned_inputs), outputs=tuple(outputs))
        txid_bytes = hash_bytes(serialize_tx(unsigned_tx, include_signatures=False))

        signed_inputs = [
            TxInput(
                outpoint=inp.outpoint,
                unlock_pubkey=inp.unlock_pubkey,
                signature=sign(signer.secret, txid_bytes),
            )
            for inp in unsigned_inputs
        ]
        return cls(inputs=tuple(signed_inputs), outputs=tuple(outputs))


_U32 = struct.Struct("<I")
_U64 = struct.Struct("<Q")


def _encode_bytes(data: bytes) -> bytes:
    """Length-prefixed byte string: u32 LE length + raw bytes."""
    return _U32.pack(len(data)) + data


def _encode_int(value: int, width: int) -> bytes:
    """Fixed-width little-endian integer."""
    return value.to_bytes(width, byteorder="little", signed=False)


def serialize_tx(tx: Transaction, include_signatures: bool) -> bytes:
    """Return a canonical, length-prefixed serialization of ``tx``.

    The serialization is deterministic: inputs in order, then outputs in order.
    When ``include_signatures`` is False, all input signatures are serialized as
    empty byte strings. This yields the hash preimage used for signing and txid.
    """
    data = b""

    data += _encode_bytes(_U32.pack(len(tx.inputs)))
    for tx_in in tx.inputs:
        data += _encode_bytes(bytes.fromhex(tx_in.outpoint.txid))
        data += _encode_bytes(_encode_int(tx_in.outpoint.index, 4))
        data += _encode_bytes(tx_in.unlock_pubkey)
        if include_signatures:
            data += _encode_bytes(tx_in.signature)
        else:
            data += _encode_bytes(b"")

    data += _encode_bytes(_U32.pack(len(tx.outputs)))
    for tx_out in tx.outputs:
        data += _encode_bytes(_encode_int(tx_out.value, 8))
        data += _encode_bytes(tx_out.lock)

    return data


def txid(tx: Transaction) -> str:
    """Return the 64-character hex SHA-256 txid of ``tx``.

    The txid excludes signatures to avoid circular dependencies during signing.
    """
    return sha256_hex(serialize_tx(tx, include_signatures=False))
