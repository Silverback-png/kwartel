"""Demo script for kwartel.crypto."""

from kwartel.crypto.keys import (
    generate_keypair,
    sign,
    verify,
    address,
)


def main() -> None:
    kp = generate_keypair()
    addr = address(kp.public)
    message = b"Kwartel Phase 1 Task 01 demo"
    signature = sign(kp.secret, message)
    valid = verify(kp.public, message, signature)

    print(f"public (hex): {kp.public.hex()}")
    print(f"address:      {addr}")
    print(f"message:      {message!r}")
    print(f"signature:    {signature.hex()}")
    print(f"verified:     {valid}")



if __name__ == "__main__":
    main()
