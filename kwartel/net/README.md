# Kwartel Networking Layer (`kwartel/net`)

Phase 2 replaces the Phase 1 in-memory `NetworkBus` with real TCP on localhost.
This package provides only the transport: binary framing, the magic/genesis
handshake, peer lifecycle, and a message relay. Block/tx gossip over TCP is a
later task.

## Why length-prefixed framing (not a delimiter)

A naive protocol might separate messages with a delimiter such as a newline or a
JSON boundary, but Kwartel messages are **arbitrary binary** (serialized blocks
and transactions). Any byte value can appear inside a payload, so a delimiter
would have to be escaped — and an escaping bug is a classic source of framing
attacks.

Instead every message is:

```
[u32 LE payload_len][u16 LE topic_id][payload]
```

- The reader knows exactly how many bytes to expect before it allocates.
- Truncation is detected immediately (we asked for N bytes and got fewer).
- There is no ambiguity about where one message ends and the next begins.
- The length is capped at `MAX_PAYLOAD` (8 MiB) before any allocation, so a peer
  cannot ask us to buffer an unbounded amount of data.

## Why magic + genesis hash in the handshake

Before any other message flows, both sides exchange:

```
HANDSHAKE:      {magic, version, node_id, genesis_hash, listen_port}
HANDSHAKE_ACK:  {magic, version, node_id, genesis_hash, listen_port}
```

- **magic** (`0x4B575431`, "KWT1") is a cheap first filter: a service that is not
  a Kwartel node will send different bytes and be disconnected immediately.
- **genesis_hash** is the transport-level chain identity. Two nodes on different
  networks have different genesis blocks and must never gossip with each other.
  Checking it here means cross-chain peers are refused before a single block or
  transaction is exchanged.
- **version** is matched exactly (same-version policy for Phase 2; negotiation
  comes later).
- **node_id** identifies the peer for the `PeerBook` and lets a node refuse a
  self-connection (remote `node_id ==` our own) and duplicate peers.

## Why inbound data is treated as hostile

`transport ≠ trust`: any peer can send any bytes. Every inbound message is
therefore:

- **size-limited** — a declared length over `MAX_PAYLOAD` closes the peer.
- **timeout-bound** — a read that stalls beyond the idle timeout (or a handshake
  beyond the handshake timeout) closes the peer, so a dead or silent peer cannot
  hold a socket (and a read-loop task) forever.
- **validated exactly like locally-produced data** — framing, topic ids, and
  handshake fields are all checked with the same code paths used on the sending
  side. Unknown topic ids, bad field lengths, and trailing bytes are errors.

A malformed message means *disconnect that peer*, never crash the node. The
server wraps every connection handler so that a `ProtocolError`, `HandshakeError`,
`TimeoutError`, or `ConnectionError` only tears down the offending connection.
