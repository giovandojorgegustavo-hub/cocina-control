"""Authentication endpoints: login and logout."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.db import get_session
from cocina_control.models.user import User
from cocina_control.security.passwords import verify_password
from cocina_control.security.rate_limit import is_allowed
from cocina_control.security.tokens import create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Generic message used for BOTH wrong password AND unknown email so that
# callers cannot enumerate registered users by observing different responses.
_AUTH_ERROR = "Invalid email or password"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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

    # --- Verify ---
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_AUTH_ERROR)

    token = create_access_token(user.id, user.role)
    return LoginResponse(token=token, role=user.role, user_id=str(user.id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> None:
    """End the session.

    v0.2 implementation: tokens are short-lived (8 h by default) and we rely
    on the client discarding the token.  No server-side blacklist or Redis is
    used here — that would be over-engineering for the current scale.
    If real token revocation is required in the future (e.g. forced logout
    across devices), implement a Redis-backed blacklist at that point.
    """
    return None
