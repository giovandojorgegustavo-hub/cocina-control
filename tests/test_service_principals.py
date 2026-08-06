"""Tests for service-principal authentication and the X-Act-As header.

The feature exists to keep one property true: a row written through the
WhatsApp assistant must be indistinguishable, in the audit trail, from a row
the cocinero wrote by hand.  ``test_write_is_attributed_to_the_human`` is the
test that proves it; everything else guards the edges around it.
"""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from cocina_control.models.service_principal import ServicePrincipal
from cocina_control.security.service_tokens import (
    SERVICE_TOKEN_PREFIX,
    generate_service_token,
    hash_service_token,
    is_service_token,
)

from .conftest import create_test_user

PRODUCTS_URL = "/api/v1/products"
COUNTS_URL = "/api/v1/inventory-counts"


def create_service_principal(
    session: Session,
    name: str = "bonabowlinterno",
    is_active: bool = True,
) -> tuple[ServicePrincipal, str]:
    """Insert a service principal; return it together with its plaintext token."""
    token = generate_service_token()
    principal = ServicePrincipal(
        id=uuid.uuid4(),
        name=name,
        token_hash=hash_service_token(token),
        is_active=is_active,
    )
    session.add(principal)
    session.flush()
    return principal, token


@pytest.fixture
def service_token(db_session: Session) -> str:
    _, token = create_service_principal(db_session, name=f"bot-{uuid.uuid4().hex[:6]}")
    return token


def svc_headers(token: str, act_as: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if act_as is not None:
        headers["X-Act-As"] = act_as
    return headers


# ---------------------------------------------------------------------------
# The property the feature exists for
# ---------------------------------------------------------------------------


async def test_write_is_attributed_to_the_human_not_the_service(
    client, db_session: Session, service_token: str, cocinero_user
):
    """A count started through the assistant is owned by the cocinero.

    If this ever fails, the audit trail is lying about who did the work — the
    exact failure the whole design is meant to prevent.
    """
    response = await client.post(
        COUNTS_URL, headers=svc_headers(service_token, cocinero_user.email)
    )
    assert response.status_code == 201

    count_id = uuid.UUID(response.json()["id"])
    created_by = db_session.scalar(
        sa.text("SELECT created_by FROM inventory_counts WHERE id = :id").bindparams(id=count_id)
    )
    assert created_by == cocinero_user.id


# ---------------------------------------------------------------------------
# Service-token authentication
# ---------------------------------------------------------------------------


async def test_service_token_with_act_as_is_authenticated(
    client, service_token: str, cocinero_user
):
    response = await client.get(
        PRODUCTS_URL, headers=svc_headers(service_token, cocinero_user.email)
    )
    assert response.status_code == 200


async def test_service_token_without_act_as_is_rejected(client, service_token: str):
    """A service token alone names nobody — it must not authenticate."""
    response = await client.get(PRODUCTS_URL, headers=svc_headers(service_token))
    assert response.status_code == 401
    assert "X-Act-As" in response.json()["detail"]


async def test_unknown_service_token_is_rejected(client, cocinero_user):
    response = await client.get(
        PRODUCTS_URL,
        headers=svc_headers(f"{SERVICE_TOKEN_PREFIX}not-a-real-token", cocinero_user.email),
    )
    assert response.status_code == 401


async def test_revoked_service_token_is_rejected(client, db_session: Session, cocinero_user):
    """Revocation takes effect immediately — no waiting for an expiry."""
    _, token = create_service_principal(db_session, name="revoked-bot", is_active=False)
    response = await client.get(PRODUCTS_URL, headers=svc_headers(token, cocinero_user.email))
    assert response.status_code == 401


async def test_act_as_is_case_insensitive(client, service_token: str, cocinero_user):
    """Matches ix_users_email_lower, the index that enforces email uniqueness."""
    response = await client.get(
        PRODUCTS_URL, headers=svc_headers(service_token, cocinero_user.email.upper())
    )
    assert response.status_code == 200


async def test_act_as_tolerates_surrounding_whitespace(client, service_token: str, cocinero_user):
    response = await client.get(
        PRODUCTS_URL, headers=svc_headers(service_token, f"  {cocinero_user.email}  ")
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Privilege boundaries
# ---------------------------------------------------------------------------


async def test_service_token_cannot_act_as_owner(client, service_token: str, owner_user):
    """The assistant captures data; it must never reach the money side."""
    response = await client.get(PRODUCTS_URL, headers=svc_headers(service_token, owner_user.email))
    assert response.status_code == 403


async def test_service_token_cannot_act_as_admin(client, service_token: str, admin_user):
    response = await client.get(PRODUCTS_URL, headers=svc_headers(service_token, admin_user.email))
    assert response.status_code == 403


async def test_act_as_unknown_email_is_401_not_404(client, service_token: str):
    """A valid service token must not become an oracle for which emails exist."""
    response = await client.get(
        PRODUCTS_URL, headers=svc_headers(service_token, "nobody@nowhere.test")
    )
    assert response.status_code == 401


async def test_user_jwt_ignores_act_as_header(client, cocinero_token: str, owner_user):
    """A logged-in human cannot borrow the header to become someone else.

    Without this, any cocinero who noticed X-Act-As in the API docs could
    escalate to owner by adding one header.
    """
    response = await client.get(
        PRODUCTS_URL,
        headers={
            "Authorization": f"Bearer {cocinero_token}",
            "X-Act-As": owner_user.email,
        },
    )
    # The request succeeds as the cocinero — the header is simply not read.
    assert response.status_code == 200


async def test_user_jwt_with_act_as_does_not_gain_owner_access(
    client, db_session: Session, cocinero_token: str, owner_user
):
    """The same escalation attempt, verified against an owner-only endpoint."""
    other = create_test_user(db_session, "owner", f"owner2-{uuid.uuid4().hex[:6]}@test.com")
    response = await client.get(
        "/api/v1/dashboard/summary",
        headers={
            "Authorization": f"Bearer {cocinero_token}",
            "X-Act-As": other.email,
        },
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Token primitives
# ---------------------------------------------------------------------------


def test_generated_tokens_are_unique_and_prefixed():
    tokens = {generate_service_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(t.startswith(SERVICE_TOKEN_PREFIX) for t in tokens)


def test_is_service_token_rejects_a_jwt():
    """A JWT is dot-separated base64 and can never take the service path."""
    from cocina_control.security.tokens import create_access_token

    jwt_token = create_access_token(uuid.uuid4(), "cocinero")
    assert not is_service_token(jwt_token)
    assert is_service_token(generate_service_token())


def test_hash_is_stable_and_does_not_contain_the_plaintext():
    token = generate_service_token()
    digest = hash_service_token(token)
    assert digest == hash_service_token(token)
    assert len(digest) == 64
    assert token not in digest
    assert token.removeprefix(SERVICE_TOKEN_PREFIX) not in digest
