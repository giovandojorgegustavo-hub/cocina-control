"""FastAPI dependency functions for authentication and authorization."""

import uuid
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from cocina_control.db import get_session
from cocina_control.models.user import User
from cocina_control.security.tokens import TokenError, decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    session: Annotated[Session, Depends(get_session)],
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    """Validate JWT and return the corresponding User from the database.

    Always returns 401 on any token failure — never 500.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except TokenError:
        raise credentials_error

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise credentials_error

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_error

    user = session.get(User, user_id)
    if user is None:
        raise credentials_error

    return user


def require_role(role: Literal["operator", "owner"]):
    """Return a dependency that enforces *role* access.

    The role is intentionally read from the database (user.role), NOT from the
    JWT claim.  This ensures that if a user's role is downgraded (e.g. owner ->
    operator), the change takes effect immediately on the next request without
    waiting for the token to expire.
    """

    def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _dep
