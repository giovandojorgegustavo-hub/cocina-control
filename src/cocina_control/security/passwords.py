"""Password hashing with bcrypt.

Uses the `bcrypt` package directly (passlib 1.7.x is not compatible with
bcrypt >= 4.0 and is in maintenance-only mode).

Default work factor is 12 rounds.  Tests that need faster hashing should
monkeypatch BCRYPT_ROUNDS:

    import cocina_control.security.passwords as pw
    pw.BCRYPT_ROUNDS = 4
"""

import bcrypt

BCRYPT_ROUNDS: int = 12

# bcrypt silently truncates inputs longer than 72 bytes.  We enforce this
# limit explicitly so callers get a clear error instead of silent truncation.
_BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*.

    Raises ValueError if *plain* encodes to more than 72 bytes (bcrypt limit).
    """
    encoded = plain.encode()
    if len(encoded) > _BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Password exceeds bcrypt limit of {_BCRYPT_MAX_BYTES} bytes "
            f"(got {len(encoded)} bytes). Use a shorter password."
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*.

    Raises ValueError if *plain* encodes to more than 72 bytes (bcrypt limit).
    """
    encoded = plain.encode()
    if len(encoded) > _BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Password exceeds bcrypt limit of {_BCRYPT_MAX_BYTES} bytes "
            f"(got {len(encoded)} bytes). Use a shorter password."
        )
    return bcrypt.checkpw(encoded, hashed.encode())
