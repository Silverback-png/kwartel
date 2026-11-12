# kwartel.transaction

UTXO transaction model, validation rules, UTXO set, and mempool for Kwartel.

## UTXO vs account model

In an account model, balances are stored as a single number per address and
updated in place. In the UTXO model used here, there are no balances stored by
the protocol. A wallet's balance is the sum of all unspent outputs it can
unlock. Spending consumes whole outputs and creates new ones; change must be sent
back to the sender explicitly. This makes double-spends explicit: the same output
can only be spent once, ever.

## Why does the txid exclude signatures?

The txid is the hash used both as the transaction identifier and as the message
signed by each input. If signatures were included in the hash, a signer would
need to know every other signature before signing their own input, creating a
circular dependency. Excluding signatures lets each input sign the same txid
independently, which is the standard Bitcoin design.

## Why does conservation matter?

Conservation — total outputs ≤ total inputs — is the rule that prevents coins
from being created from nothing. Every kwart in an output must come from a
previously unspent output. The difference between inputs and outputs is the fee,
which must be ≥ 0. A negative fee would mean the transaction mints money.

## What is a double-spend, and where do we stop it?

A double-spend tries to use the same output in two different transactions. We
stop it in two places:

1. **Mempool:** `Mempool.accept()` rejects a transaction if any of its inputs are
   already consumed by another transaction in the mempool.
2. **UTXO set:** `UTXOSet.apply_transaction()` validates the transaction and
   removes spent outpoints atomically. A second attempt to spend the same
   outpoint will fail because it is no longer in the set.

## Why must validation return a list instead of raising?

Consensus code receives untrusted transactions from the network. Returning a
list of all violations lets the caller inspect every problem at once and never
crashes on malformed input. This is safer than exceptions for block and
mempool handling.
