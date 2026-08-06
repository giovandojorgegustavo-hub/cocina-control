"""Generation and hashing of service-principal tokens.

This module is pure domain logic: it does NOT raise HTTPException and does not
touch the database.  Callers (api/deps.py) translate failures into HTTP
responses.

Why SHA-256 and not bcrypt
--------------------------
passwords.py uses bcrypt because human passwords have low entropy and must be
expensive to guess.  A service token is 256 bits of `secrets` randomness —
there is nothing to brute-force, so a slow KDF buys no security while adding
~100 ms to every write the assistant makes.  Storing a fast digest of a
high-entropy secret is the same tradeoff GitHub and Stripe make for API
tokens.  If this ever holds a human-chosen value, switch to bcrypt.
"""

import hashlib
import secrets

# Distinguishes a service token from a user JWT at a glance — both in the
# Authorization header and in any log or config file it lands in.  A JWT is
# three base64 segments separated by dots and can never collide with this.
SERVICE_TOKEN_PREFIX = "svc_"

# 32 bytes -> 43 urlsafe base64 chars.  256 bits of entropy.
_TOKEN_BYTES = 32


def generate_service_token() -> str:
    """Return a fresh plaintext service token.  Show once, store never."""
    return f"{SERVICE_TOKEN_PREFIX}{secrets.token_urlsafe(_TOKEN_BYTES)}"


def hash_service_token(token: str) -> str:
    """Return the SHA-256 hex digest used as the database lookup key."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_service_token(token: str) -> bool:
    """Return True if *token* is shaped like a service token.

    Only decides which authentication path to take — never grants access.
    """
    return token.startswith(SERVICE_TOKEN_PREFIX)
