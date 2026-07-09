"""Authentication endpoints: login and logout."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.api.deps import get_current_user
from cocina_control.db import get_session
from cocina_control.models.user import User
from cocina_control.security.passwords import hash_password, verify_password
from cocina_control.security.rate_limit import is_allowed
from cocina_control.security.tokens import create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Generic message used for BOTH wrong password AND unknown email so that
# callers cannot enumerate registered users by observing different responses.
_AUTH_ERROR = "Invalid email or password"

# Pre-computed dummy hash used when a login email is not found.
# This ensures verify_password() is always called regardless of whether the
# user exists, making the response time constant and preventing timing-based
# user enumeration.  Computed once at import time to avoid adding startup cost.
_DUMMY_PASSWORD_HASH = hash_password("this-is-a-constant-time-dummy-hash-not-a-real-password")


class LoginRequest(BaseModel):
    email: EmailStr
    # min_length=1: reject empty passwords at the validation layer (422).
    # max_length=128: reject inputs that would cause bcrypt to raise ValueError
    # (bcrypt limit is 72 bytes; 128 chars is generous while preventing abuse).
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    token: str
    role: str
    user_id: str


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> LoginResponse:
    """Authenticate a user and return a JWT.

    Rate-limited: max 5 attempts per minute per IP.
    Email is normalized to lowercase before lookup (see User model docstring).

    Timing-safe: verify_password() is always called even when the email does
    not exist (using a dummy hash) so that response latency does not reveal
    whether an account is registered.
    """
    # --- Rate limiting ---
    client_ip = request.client.host if request.client else "unknown"
    if not is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait a minute.",
        )

    # --- Lookup ---
    email = body.email.lower()
    stmt = select(User).where(User.email == email)
    user = session.scalar(stmt)

    # --- Constant-time verify ---
    # Always call verify_password to prevent timing-based user enumeration.
    stored_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
    password_matches = verify_password(body.password, stored_hash)
    if user is None or not password_matches:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_AUTH_ERROR)

    token = create_access_token(user.id, user.role)
    return LoginResponse(token=token, role=user.role, user_id=str(user.id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user: Annotated[User, Depends(get_current_user)]) -> None:
    """End the session.

    Requires a valid Bearer token — returns 401 if missing or invalid.

    v0.2 implementation: tokens are short-lived (8 h by default) and we rely
    on the client discarding the token.  No server-side blacklist or Redis is
    used here — that would be over-engineering for the current scale.
    If real token revocation is required in the future (e.g. forced logout
    across devices), implement a Redis-backed blacklist at that point.
    """
    return None
