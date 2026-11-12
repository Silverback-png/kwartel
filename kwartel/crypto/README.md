# kwartel.crypto

Cryptographic primitives for the Kwartel blockchain: Ed25519 keypairs,
detached signatures, SHA-256 helpers, and Base58Check addresses.

## Why Ed25519?

Ed25519 is a modern, deterministic, high-security digital signature scheme. It
uses fast, constant-time implementations, compact 32-byte public keys and
64-byte signatures, and avoids many pitfalls of ECDSA (e.g., nonce reuse and
non-canonical signature encodings). For an educational chain it is simpler to
reason about and harder to misuse than secp256k1.

## Why is the secret a 32-byte seed?

Ed25519 internally expands a 32-byte seed into a 64-byte signing key
(seed || public key). Storing only the seed is the minimal wallet backup: it is
shorter, easier to write down, and fully deterministic. Any node can re-derive
the public key and signing key from the seed alone, so the seed is the wallet.

## Why Base58Check for addresses?

Base58 avoids visually ambiguous characters (0/O, I/l) and omits characters that
could be awkward in URLs or double-click selection, making human transcription
safer than Base64. The four-byte double-SHA256 checksum protects against simple
typos and copy-paste errors: a random address change has only a 1/2^32 chance
of remaining valid, so wallets can reject accidentally mistyped addresses before
any transaction is created.

## Why must `verify()` return `False` instead of raising?

Consensus code receives untrusted data from the network. If malformed signatures
or public keys raise exceptions, an attacker can crash or slow a node by sending
bad inputs. Returning `False` makes verification a pure boolean decision and
lets callers handle failure uniformly, which is safer for block and transaction
validation.
