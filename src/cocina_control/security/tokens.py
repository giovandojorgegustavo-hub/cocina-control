"""JWT creation and validation.

This module is pure domain logic: it does NOT raise HTTPException.
Callers (FastAPI dependencies in api/deps.py) are responsible for
translating TokenError into the appropriate HTTP response.
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from cocina_control.config import get_settings


class TokenError(Exception):
    """Raised when a JWT is invalid, expired, or tampered with."""


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """Return a signed JWT with sub, role, iat, and exp claims."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate *token*.  Raises TokenError on any failure."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid") from exc
