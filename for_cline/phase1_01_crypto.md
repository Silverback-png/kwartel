# Project Kwartel (KWT) — Phase 1, Task 01: Crypto Module

> **Model tier:** Sonnet 5 (standard). This is a foundational but not consensus-critical task.
>
> **Cline instructions:** Read this file completely before writing any code.
> Follow TDD strictly: write each test, watch it fail, then implement, then pass.
> Write your progress and any deviations to `FINDINGS.md` (append, don't overwrite).
> Do NOT git commit — leave that to the operator.

## Context

We are building **Kwartel**, a from-scratch blockchain. Phase 1 is an educational
chain in Python 3.11. This is the very first module: cryptographic keys and
signatures. Everything else (transactions, blocks, consensus) depends on it.

**Non-negotiables:**
- Use an audited library. **PyNaCl** (libsodium bindings) for Ed25519. Never implement crypto yourself.
- Deterministic serialization (canonical byte encoding) everywhere — consensus depends on it.
- Type hints on every public function.
- Python 3.11, `pytest` for tests.

## Setup

```bash
cd C:\Users\TTEMPESTT\kwartel
python -m venv .venv
.venv\Scripts\activate
pip install pynacl pytest
pip freeze > requirements.txt
```

## Deliverables

### Files to create
- `kwartel/crypto/keys.py` — keypair generation, signing, verification
- `kwartel/crypto/__init__.py`
- `tests/crypto/test_keys.py`
- `kwartel/crypto/README.md` — short design note (see end)

### Task 1: Key generation

**Test first:**
```python
def test_generate_keypair_returns_distinct_pairs():
    kp1 = generate_keypair()
    kp2 = generate_keypair()
    assert kp1.secret != kp2.secret
    assert kp1.public != kp2.public

def test_public_key_derivable_from_secret():
    kp = generate_keypair()
    assert derive_public(kp.secret) == kp.public
```

**Implement:**
- `generate_keypair() -> KeyPair` — 32-byte random Ed25519 secret (use `nacl.bindings.crypto_sign_seed_keypair` with `os.urandom(32)` so the seed IS the secret key — this matters later for wallet backup: the 32-byte seed is the wallet).
- Dataclass `KeyPair(secret: bytes, public: bytes)` with both exactly 32 bytes.
- `derive_public(secret: bytes) -> bytes`.

### Task 2: Signing and verification

**Test first (must include these cases):**
```python
def test_sign_and_verify_roundtrip(): ...          # sign then verify -> True
def test_verify_fails_on_tampered_message(): ...   # flip one message byte -> False
def test_verify_fails_on_wrong_key(): ...          # verify with different pubkey -> False
def test_verify_fails_on_tampered_signature(): ... # flip one sig byte -> False
def test_signature_is_64_bytes(): ...
def test_sign_is_deterministic(): ...              # same key + msg = same signature (Ed25519 is deterministic)
```

**Implement:** `sign(secret: bytes, message: bytes) -> bytes` and `verify(public: bytes, message: bytes, signature: bytes) -> bool`. Verify must return `False` on ANY malformed input — never raise. Use `nacl.bindings.crypto_sign_verify_detached` inside try/except.

### Task 3: Canonical serialization helpers

Consensus requires every node to serialize a structure identically. Build the primitive now:

```python
def hash_bytes(data: bytes) -> bytes   # SHA-256, returns 32 raw bytes
def sha256_hex(data: bytes) -> str
```

**Test:** known-vector check — `sha256_hex(b"")` == `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

### Task 4: Address format

An address is a human-usable representation of a public key:

- `address(public: bytes) -> str` = `"KWT" + base58check(version_byte + public_key)` where version_byte = `\x00`, and base58check = Base58(payload + first 4 bytes of sha256(sha256(payload))).
- Implement Base58 yourself in `kwartel/crypto/base58.py` (it's an encoding, not crypto — safe and educational), with roundtrip + invalid-checksum tests. Include the standard Bitcoin alphabet `123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz`.
- `validate_address(addr: str) -> bool` — checks prefix, checksum. Must never raise.

## Acceptance criteria

1. `pytest tests/crypto/ -v` — all pass
2. No imports outside stdlib + pynacl
3. All public functions type-hinted
4. A demo in `kwartel/crypto/__main__.py`: generate keypair, print address, sign a message, verify it. Run it, paste output into FINDINGS.md.

## Design note (kwartel/crypto/README.md)

Answer in 5-10 short paragraphs: Why Ed25519 over secp256k1? Why is the secret a 32-byte seed? Why base58check (what does the checksum protect against, what does base58 avoid vs base64)? Why must verify() return False instead of raising?
