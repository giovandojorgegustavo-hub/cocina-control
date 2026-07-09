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


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())
