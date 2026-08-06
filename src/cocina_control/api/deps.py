"""FastAPI dependency functions for authentication and authorization."""

import logging
import uuid
from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from cocina_control.db import get_session
from cocina_control.models.service_principal import ServicePrincipal
from cocina_control.models.user import User
from cocina_control.security.service_tokens import hash_service_token, is_service_token
from cocina_control.security.tokens import TokenError, decode_token

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

RoleName = Literal["cocinero", "owner", "admin"]

# Roles a service principal is allowed to impersonate.
#
# Deliberately capture-only.  The assistant exists to write down what kitchen
# staff dictate; it has no business validating a delivery (owner) or reading
# cost data (admin).  Keeping this at cocinero means a leaked service token
# cannot reach the money side of the system.  Widening it is a code change
# that goes through review — not a database edit someone makes at 2am.
ACT_AS_ALLOWED_ROLES: frozenset[str] = frozenset({"cocinero"})


def get_current_user(
    session: Annotated[Session, Depends(get_session)],
    token: Annotated[str, Depends(oauth2_scheme)],
    act_as: Annotated[str | None, Header(alias="X-Act-As")] = None,
) -> User:
    """Return the acting User for this request.

    Two credential shapes are accepted:

    - A user JWT, issued by /auth/login.  X-Act-As is ignored on this path,
      so a logged-in cocinero can never impersonate a colleague by adding
      the header.
    - A service token (svc_...), which MUST name the acting user via X-Act-As.

    Always returns 401 on any credential failure — never 500.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if is_service_token(token):
        return _resolve_acting_user(session, token, act_as, credentials_error)

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


def _resolve_acting_user(
    session: Session,
    token: str,
    act_as: str | None,
    credentials_error: HTTPException,
) -> User:
    """Authenticate a service token and resolve the user it acts for.

    The returned object is an ordinary User, so every downstream role check
    and every created_by foreign key behaves exactly as it would for a human
    session.  That is the whole point: the audit trail must not be able to
    tell the difference.
    """
    # act_as se valida ANTES de buscar el token, y el orden importa.
    #
    # Al reves, un token valido sin X-Act-As daba un 401 con mensaje distinto
    # al de un token invalido. Esa diferencia convierte al endpoint en un
    # oraculo: quien encuentre un token filtrado puede confirmar que sigue
    # activo sin conocer el correo de nadie. El mensaje util se va al log del
    # servidor, donde lo ve el operador y no quien prueba credenciales.
    if not act_as:
        logger.warning("Service token presented without X-Act-As header")
        raise credentials_error

    principal = session.scalar(
        sa.select(ServicePrincipal).where(
            ServicePrincipal.token_hash == hash_service_token(token),
            ServicePrincipal.is_active.is_(True),
        )
    )
    if principal is None:
        raise credentials_error

    # Case-insensitive to match ix_users_email_lower, the index that enforces
    # email uniqueness.
    user = session.scalar(
        sa.select(User).where(sa.func.lower(User.email) == act_as.strip().lower())
    )
    if user is None:
        # Deliberately the same 401 as a bad token: a valid service token must
        # not become an oracle for which emails exist.
        raise credentials_error

    if user.role not in ACT_AS_ALLOWED_ROLES:
        logger.warning(
            "Service principal %s refused act-as for %s (role=%s)",
            principal.name,
            user.email,
            user.role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Service tokens may only act as cocinero",
        )

    # The database row will name the human.  This log line is the only place
    # that records the request arrived through a service — keep it.
    logger.info("Service principal %s acting as %s", principal.name, user.email)
    return user


def require_role(role: RoleName):
    """Return a dependency that enforces *role* access.

    The role is intentionally read from the database (user.role), NOT from the
    JWT claim.  This ensures that if a user's role is downgraded (e.g. owner ->
    cocinero), the change takes effect immediately on the next request without
    waiting for the token to expire.
    """

    def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _dep


def require_any_role(*roles: RoleName):
    """Return a dependency that allows access if the user has ANY of the given roles.

    Useful for endpoints reachable by more than one role (e.g. owner or admin).
    Same DB-first check as require_role: the role is read from the database,
    not from the JWT claim, so role changes take effect immediately.
    """
    if not roles:
        raise ValueError("require_any_role requires at least one role")
    allowed = frozenset(roles)

    def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _dep
